"""Does the shortcut actually fire? Registration is not the same thing.

The self-test asks macOS to register CTRL+CMD+T and reports success when it
says yes. It said yes for days while the shortcut did nothing, because a
hotkey can be registered in a process that will never receive it. The only
honest test is a person pressing the key and the app noticing.

So this starts the real hotkey manager — the same code path the app uses, not
a simplified copy — and waits.
"""
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

WAIT_SECONDS = 20


# Both keys of every pair. The first version of this asked only about the
# left-hand key of each, and told somebody their Command key had never been
# pressed — on a Mac they had been using all day — because they hold the
# right one. A tool that reports a confident wrong answer is worse than one
# that reports nothing, because it is acted upon.
SIDES = {
    "ctrl": ("ctrl", "rctrl"),
    "cmd": ("cmd", "rcmd"),
    "shift": ("shift", "rshift"),
    "alt": ("alt", "ralt"),
}

# Fast enough that an ordinary keypress cannot fall between two samples.
# This is a sampler, not a record of events: at 0.2s a 100ms tap was
# invisible, so "never arrived" could simply mean "not while I was
# looking". Which it also said, confidently.
POLL = 0.02

# Long enough that the answer is about the keyboard rather than about
# reaction time.
HOLD_SECONDS = 3


def modifiers_down():
    """Which modifiers are held right now, either hand."""
    from app import platform_util
    down = set()
    for name, keys in SIDES.items():
        for key in keys:
            try:
                if platform_util.key_is_down(key):
                    down.add(name)
                    break
            except Exception:
                pass
    return down


def watch_modifiers(wanted):
    """Ask for the modifiers on their own, and watch for them.

    Separated from the shortcut itself deliberately. Pressing a whole
    shortcut answers two questions at once and tells you neither: if
    nothing happens you cannot say whether the keys arrived and the
    delivery failed, or the keys never arrived. Held on their own, with
    nothing else to go wrong, the answer means one thing.
    """
    if not wanted:
        return set()
    print("  ==========================================================")
    print("    First, a keyboard check.")
    print()
    print("    HOLD DOWN %s together for %d seconds."
          % (" + ".join(m.upper() for m in sorted(wanted)), HOLD_SECONDS))
    print("    Either side of the keyboard. Nothing else, no letter.")
    print("  ==========================================================")
    print()
    seen, deadline = set(), time.time() + HOLD_SECONDS + 12
    started = None
    while time.time() < deadline:
        time.sleep(POLL)
        down = modifiers_down()
        seen |= down
        if wanted <= down:
            started = started or time.time()
            if time.time() - started >= 0.3:
                break
        sys.stdout.write("\r  holding: %-30s"
                         % (", ".join(sorted(down)) or "nothing yet"))
        sys.stdout.flush()
    print("\r" + " " * 50)
    return seen


def modifiers_of(spec):
    """The modifier names a shortcut asks for."""
    names = {"ctrl": "ctrl", "control": "ctrl", "cmd": "cmd",
             "super": "cmd", "win": "cmd", "shift": "shift",
             "alt": "alt", "option": "alt"}
    return {names[part] for part in str(spec).lower().split("+")
            if part.strip() in names}


def report_modifiers(specs, held):
    """Say which modifier keys actually reached this machine.

    The one question nobody could answer while a shortcut was dead: was the
    key even arriving? A missing Ctrl and a broken listener produce exactly
    the same silence, and until this line existed they were told apart by
    guessing.
    """
    from app import platform_util
    if not platform_util.IS_MAC:
        return
    wanted = set()
    for spec in specs.values():
        wanted |= modifiers_of(spec)
    if not wanted:
        return
    print("  Modifier keys this Mac reported:")
    for mod in sorted(wanted):
        mark = "arrived" if mod in held else "NOT SEEN"
        print("      %-6s %s" % (mod, mark))
    missed = sorted(wanted - held)
    if missed:
        print()
        print("  %s did not reach this Mac while you were holding it."
              % " and ".join(m.upper() for m in missed))
        print("  If that key works elsewhere, tell whoever is helping —")
        print("  it means this check is wrong, not your keyboard. If it")
        print("  does not, look at System Settings > Keyboard >")
        print("  Modifier Keys, and at the key itself.")
    print()


def main():
    from app import config, hotkey, platform_util

    # BOTH shortcuts, because they are registered together and one can fail
    # while the other works — which is exactly what happened to the
    # clipboard shortcut while the snip one was fine.
    specs = {
        "snip": config.CONFIG["hotkey"],
        "clipboard": config.CONFIG["hotkey_clipboard"],
    }
    spec = specs["snip"]
    fired = threading.Event()
    presses = []
    seen = {}
    ids = {}

    manager = hotkey.HotkeyManager()

    def make(name):
        def handler():
            seen[name] = seen.get(name, 0) + 1
            presses.append(time.time())
            fired.set()
        return handler

    for name, value in specs.items():
        try:
            ids[name] = manager.register(value, make(name))
        except Exception as exc:
            print("  could not register %s (%s): %s" % (name, value, exc))
    manager.start()

    if not manager.wait_ready(8.0):
        print("  The listener did not start within 8 seconds.")
        return 2

    backend = getattr(manager, "backend", "?")
    print()
    print("  Listener started.  Backend: %s" % backend)
    if backend == "carbon":
        print("  (registered with macOS directly - no permission needed)")
    elif backend == "watcher":
        print("  (watching the keyboard - needs Accessibility permission)")
    print()
    wanted = set()
    for value in specs.values():
        wanted |= modifiers_of(value)
    held = watch_modifiers(wanted) if platform_util.IS_MAC else set()
    print("  ==========================================================")
    print("    Now the shortcuts. PRESS BOTH, one after the other:")
    print()
    for name, value in specs.items():
        print("      %-10s %s" % (name, value.upper()))
    print()
    print("    Anywhere - this window does not need to be in front.")
    print("  ==========================================================")
    print()

    # Watch the modifier keys themselves while waiting.
    #
    # Every failure this probe reported used to look the same — "nothing
    # arrived" — whether the shortcut was broken, taken by another app, or
    # simply never pressed, and it could not tell the person which. Asking
    # the window server what is held down needs no permission and no event
    # tap, so it can say "you pressed Cmd and T, no Ctrl" outright. An
    # evening went into a shortcut that no tool would answer that about.
    deadline = time.time() + WAIT_SECONDS
    while time.time() < deadline and len(seen) < len(specs):
        time.sleep(POLL)
        held |= modifiers_down()
        remaining = int(deadline - time.time())
        got = ", ".join(sorted(seen)) or "nothing yet"
        sys.stdout.write("\r  waiting ... %2ds   received: %-24s" %
                         (remaining, got))
        sys.stdout.flush()
    print("\r" + " " * 60)
    report_modifiers(specs, held)

    errors = {name: manager.error_for(hid) for name, hid in ids.items()}
    try:
        manager.stop()
    except Exception:
        pass

    for name, value in specs.items():
        mark = "  ok  " if seen.get(name) else " FAIL "
        note = ""
        if not seen.get(name):
            note = "  <- never arrived"
            if errors.get(name):
                note = "  <- %s" % errors[name]
        print("  [%s]  %-10s %s%s" % (mark, name, value.upper(), note))
    print()

    if len(seen) == len(specs):
        print("  Both shortcuts work.")
        return 0
    if seen:
        print("  One shortcut works and one does not, so the listener is")
        print("  fine — the missing combination is being taken by another")
        print("  app. Change it in Squint > Settings.")
        return 1

    error = errors.get("snip")
    print("  [ FAIL ]  Registered, but nothing arrived.")
    if error:
        print("            Reported: %s" % error)
    # Say nothing about causes when the keyboard check already contradicts
    # them. The old version printed "CMD never arrived" and then, four
    # lines later, "another app may already own CTRL+CMD+T" — two
    # confident and incompatible diagnoses in one screen, from a tool whose
    # whole purpose is to stop people guessing.
    if platform_util.IS_MAC and (wanted - held):
        print("            The keyboard check above did not see %s, so"
              % " and ".join(sorted(m.upper() for m in (wanted - held))))
        print("            work out that part first — nothing here can")
        print("            fire without it.")
    elif backend == "watcher":
        print("            The app fell back to watching the keyboard, which")
        print("            needs Accessibility permission:")
        print("            System Settings > Privacy & Security >")
        print("            Accessibility - add the app, then try again.")
    else:
        print("            Another app may already own %s." % spec.upper())
        print("            Change it in Squint > Settings and retry.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
