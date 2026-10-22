"""Global-hotkey watcher that runs in its own process.

This exists because of a hard macOS rule. pynput's macOS backend calls the
Text Input Services API from its listener thread to turn keycodes into
characters. TIS/TSM may only be used from the main thread of a UI
application, and macOS does not warn — it aborts the whole process:

    ABORT -> Text Input Sources or Text Services Manager API is being called
    in two threads concurrently.

Tk owns the main thread, so the listener can never have it. Running the
watcher as a separate, non-UI process removes the conflict completely: this
process has no GUI, so its thread is free to call TIS, and it reports
presses to the parent as plain lines on stdout.

Usage (the parent does this, not you):
    python hotkey_listener.py '{"1": "<ctrl>+<alt>+t"}'
"""
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def die_with_parent():
    """Quit the moment the app that started this is gone.

    Without it, every Squint that is force-quit, crashes, or is killed
    leaves this process behind — and a left-behind listener still holds its
    global shortcut registration with macOS. Forty of them had accumulated
    on one machine over several weeks, some from before the app was
    renamed, each one still registered for Ctrl+Cmd+T. macOS delivers the
    shortcut to one of them; that one's app has been dead for a fortnight;
    the press goes nowhere. The running Squint registers successfully,
    reports itself ready, and never hears a thing.

    That is what "the shortcut stopped working" was. Not permissions, not
    the bundle, not Carbon, not the keyboard: an orphan holding the door.

    Two ways of noticing, because one of them is not enough. getppid()
    becomes 1 when the parent dies, which is cheap and immediate — except
    where this process was re-parented for another reason. stdin closing is
    the other: the parent holds the write end of that pipe and nothing else
    does, so EOF means the parent is gone. Whichever notices first wins.
    """
    def watch():
        while True:
            time.sleep(2.0)
            try:
                if os.getppid() <= 1:
                    os._exit(0)
            except Exception:
                os._exit(0)

    def watch_stdin():
        try:
            while sys.stdin.readline():
                pass
        except Exception:
            pass
        os._exit(0)

    threading.Thread(target=watch, daemon=True).start()

    # Only when stdin is genuinely a pipe from the parent.
    #
    # It was started unconditionally, and that killed the listener on
    # every launch from the app icon. A process started by the bundle
    # inherits /dev/null for stdin; reading /dev/null returns end-of-file
    # at once; end-of-file was taken to mean "the parent has gone"; the
    # listener exited before it had registered anything. No listener
    # process, no shortcut, and a log line saying the backend was unknown.
    #
    # The parent gives this process a real pipe and holds its end open, so
    # where there is a pipe, end-of-file does mean what it says. Where
    # there is not, this says nothing and `getppid` is the whole answer.
    try:
        import stat
        if stat.S_ISFIFO(os.fstat(0).st_mode):
            threading.Thread(target=watch_stdin, daemon=True).start()
    except Exception:
        pass


def main(argv=None):
    die_with_parent()
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: hotkey_listener.py '<json map of id -> spec>'",
              file=sys.stderr)
        return 2
    try:
        payload = json.loads(argv[0])
    except Exception as exc:
        print("bad spec map: %s" % exc, file=sys.stderr)
        return 2
    # {id: {"spec": "ctrl+cmd+t", "pynput": "<ctrl>+<cmd>+t"}}
    spec_map = {k: v["spec"] for k, v in payload.items()}
    pynput_map = {k: v["pynput"] for k, v in payload.items()}

    def note(message):
        """Something the app should write in its log.

        On stdout rather than stderr, because stderr is only read once the
        child has ended — so the reason a backend was rejected arrived,
        historically, at the exact moment nobody could use it.
        """
        try:
            sys.stdout.write("NOTE %s\n" % message.replace("\n", " "))
            sys.stdout.flush()
        except Exception:
            pass

    def report(hotkey_id):
        try:
            sys.stdout.write("%s\n" % hotkey_id)
            sys.stdout.flush()
        except Exception:
            pass

    def report_up(hotkey_id):
        try:
            sys.stdout.write("UP %s\n" % hotkey_id)
            sys.stdout.flush()
        except Exception:
            pass

    # Carbon is the real macOS API: it consumes the keystroke (so the app in
    # front does not also act on it) and needs no Accessibility permission.
    # Only if it is unusable do we fall back to watching the keyboard.
    try:
        from app import hotkey_carbon
    except Exception as exc:
        hotkey_carbon = None
        note("carbon could not be loaded: %s" % exc)

    # "auto" tries Carbon and falls back; the other two pin it. A person
    # whose shortcut is dead needs to be able to try the other one without
    # waiting for a release to work out which is at fault.
    wanted = os.environ.get("SQUINT_HOTKEY_BACKEND", "auto").strip().lower()
    if wanted not in ("auto", "carbon", "watcher"):
        wanted = "auto"

    if hotkey_carbon is not None and not hotkey_carbon.AVAILABLE:
        note("carbon unusable: %s" % (hotkey_carbon._error or "unknown"))
    if wanted == "watcher":
        note("carbon skipped: asked for the watcher")
    if (wanted != "watcher" and hotkey_carbon is not None
            and hotkey_carbon.AVAILABLE):
        try:
            def ready(refused, ui_status=None):
                # Named here rather than announced blindly: the app can only
                # tell the user a shortcut was rejected if the child says
                # which ones were.
                #
                # The window-server status goes on its own line ahead of it,
                # rather than as another field on this one: READY is parsed
                # by position, and a fourth field would have quietly changed
                # what the third one means.
                if ui_status is not None:
                    sys.stdout.write("UI %s\n" % ui_status)
                # Before READY: the app knows from the first press that it
                # will be told when the shortcut is let go.
                sys.stdout.write("RELEASES\n")
                sys.stdout.write("READY carbon %s\n"
                                 % json.dumps(list(refused)))
                sys.stdout.flush()

            hotkey_carbon.listen(spec_map, report, on_ready=ready,
                                 on_release=report_up)
            return 0
        except Exception as exc:
            note("carbon failed: %s" % exc)
            print("CARBON_FAILED %s" % exc, file=sys.stderr)
            if wanted == "carbon":
                return 6          # pinned to it; do not quietly do otherwise
            # fall through to the watcher

    try:
        from pynput import keyboard
    except Exception as exc:
        print("PYNPUT_MISSING %s" % exc, file=sys.stderr)
        return 3

    def make_handler(hotkey_id):
        def fire():
            try:
                sys.stdout.write("%s\n" % hotkey_id)
                sys.stdout.flush()
            except Exception:
                pass
        return fire

    mapping = {}
    for hotkey_id, spec in spec_map.items():
        mapping[pynput_map.get(hotkey_id, spec)] = make_handler(hotkey_id)
    if not mapping:
        return 0

    try:
        listener = keyboard.GlobalHotKeys(mapping)
    except Exception as exc:
        print("LISTENER_FAILED %s" % exc, file=sys.stderr)
        return 4

    # Tell the parent we got this far, so it can distinguish "failed to
    # start" from "started but never sees keys", which is what a missing
    # Accessibility permission looks like.
    sys.stdout.write("READY watcher\n")
    sys.stdout.flush()

    try:
        listener.start()
        listener.join()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print("LISTENER_STOPPED %s" % exc, file=sys.stderr)
        return 5
    return 0


if __name__ == "__main__":
    sys.exit(main())
