"""A menu-bar icon on macOS, so the app can stay out of the way.

This is the second attempt at a status icon. The first used pystray, whose
macOS backend drives AppKit from a thread of its own — and AppKit, like the
Text Input Services API that crashed the hotkey listener, aborts the process
rather than failing politely when touched off the main thread.

The difference here is that nothing new is started: Tk's mainloop already
runs on the main thread and already pumps the AppKit run loop, so the status
item is created on that thread and serviced by that loop. No extra thread,
no second event loop.

Everything is guarded. If any of it fails the app carries on exactly as it
did before, with the Dock icon and the window.
"""
import sys
import threading

IS_MAC = sys.platform == "darwin"

_state = {"item": None, "menu": None, "target": None, "error": "",
          "on_click": None}
_lock = threading.Lock()


def available():
    if not IS_MAC:
        return False
    try:
        __import__("AppKit")
        __import__("objc")
        return True
    except Exception:
        return False


def last_error():
    return _state["error"]


def start(actions, title="⇋", on_click=None):
    """Create the status item. `actions` is [(label, callback), ...].

    A callback of None inserts a separator. Must be called on the main
    thread, which for this app means from Tk's own thread.

    With `on_click`, a click on the icon calls it (the app's small panel)
    and the menu opens on a right click or a Control-click instead. If
    the icon cannot be made to do that, it opens the menu as before.

    Returns True if the icon is now in the menu bar.
    """
    if not IS_MAC:
        _state["error"] = "not macOS"
        return False
    with _lock:
        if _state["item"] is not None:
            return True
        try:
            import objc
            from AppKit import (NSStatusBar, NSMenu, NSMenuItem,
                                NSVariableStatusItemLength)
            from Foundation import NSObject

            # One Objective-C object owns every menu action. Menu items hold
            # a weak reference to their target, so this has to be kept alive
            # in module state or the menu silently stops responding.
            class _Target(NSObject):
                def initWithHandlers_(self, handlers):
                    self = objc.super(_Target, self).init()
                    if self is None:
                        return None
                    self._handlers = handlers
                    return self

                def fire_(self, sender):
                    handler = self._handlers.get(int(sender.tag()))
                    if handler is None:
                        return
                    try:
                        handler()
                    except Exception:
                        pass

                def click_(self, sender):
                    _clicked()

            handlers = {}
            menu = NSMenu.alloc().init()
            menu.setAutoenablesItems_(False)
            target = _Target.alloc().initWithHandlers_(handlers)

            # A submenu is a label whose callback is a list of its own
            # (label, callback) pairs. The tray menu on Windows has had a
            # language switcher under "Translate into" since it was
            # written; this menu was flat, so the same app offered a way to
            # change target language on one platform and not the other.
            counter = [0]

            def build(into, entries):
                for label, callback in entries:
                    if callback is None:
                        into.addItem_(NSMenuItem.separatorItem())
                        continue
                    item = (NSMenuItem.alloc()
                            .initWithTitle_action_keyEquivalent_(
                                label,
                                objc.selector(_Target.fire_,
                                              signature=b"v@:@"), ""))
                    item.setEnabled_(True)
                    if isinstance(callback, (list, tuple)):
                        sub = NSMenu.alloc().init()
                        sub.setAutoenablesItems_(False)
                        build(sub, callback)
                        item.setSubmenu_(sub)
                    else:
                        index = counter[0]
                        counter[0] += 1
                        item.setTarget_(target)
                        item.setTag_(index)
                        handlers[index] = callback
                    into.addItem_(item)

            build(menu, actions)

            status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
                NSVariableStatusItemLength)
            button = status_item.button()
            if button is not None:
                button.setTitle_(title)
            else:                       # very old macOS
                status_item.setTitle_(title)
            _state.update({"item": status_item, "menu": menu,
                           "target": target, "error": "",
                           "on_click": on_click})
            if not (on_click and button is not None
                    and _click_opens_panel(button, target)):
                status_item.setMenu_(menu)
            return True
        except Exception as exc:
            _state["error"] = "%s: %s" % (type(exc).__name__, exc)
            return False


# A right click, or a left click with Control held, is the menu.
_RIGHT_UP = 4                   # NSEventTypeRightMouseUp
_CONTROL = 1 << 18              # NSEventModifierFlagControl


def _click_opens_panel(button, target):
    """Point the icon's click at `on_click`. False if it would not take."""
    try:
        button.setTarget_(target)
        button.setAction_("click:")
        # Left and right button, on the way up.
        button.sendActionOn_((1 << 2) | (1 << 4))
        return True
    except Exception as exc:
        _state["error"] = ""
        _state["click_error"] = "%s: %s" % (type(exc).__name__, exc)
        try:
            button.setTarget_(None)
            button.setAction_(None)
        except Exception:
            pass
        return False


def _wants_menu():
    try:
        from AppKit import NSApp
        event = NSApp.currentEvent()
        if event is None:
            return False
        return (int(event.type()) == _RIGHT_UP
                or bool(int(event.modifierFlags()) & _CONTROL))
    except Exception:
        return False


def _clicked():
    """The icon was clicked: the panel, or the menu on a right click."""
    if _wants_menu() or _state.get("on_click") is None:
        show_menu()
        return
    try:
        _state["on_click"]()
    except Exception:
        show_menu()


def show_menu():
    """Open the icon's menu under it, as a click did before the panel."""
    item, menu = _state.get("item"), _state.get("menu")
    if item is None or menu is None:
        return
    try:
        # Giving the item its menu for the length of one click is how a
        # status item opens a menu it does not open on every click.
        item.setMenu_(menu)
        item.button().performClick_(None)
    except Exception:
        try:
            item.popUpStatusItemMenu_(menu)
        except Exception:
            pass
    finally:
        try:
            item.setMenu_(None)
        except Exception:
            pass


def anchor():
    """The icon's box on the screen, (x0, y0, x1, y1) in Tk's coordinates
    (top left of the main screen, points), or None."""
    item = _state.get("item")
    if item is None:
        return None
    try:
        from AppKit import NSScreen
        button = item.button()
        frame = button.window().frame()
        screens = NSScreen.screens()
        top = screens[0].frame().size.height if screens else None
        if top is None:
            return None
        x0 = float(frame.origin.x)
        x1 = x0 + float(frame.size.width)
        y1 = float(top) - float(frame.origin.y)
        y0 = y1 - float(frame.size.height)
        return x0, y0, x1, y1
    except Exception:
        return None


def stop():
    with _lock:
        item = _state.get("item")
        if item is None:
            return
        try:
            from AppKit import NSStatusBar
            NSStatusBar.systemStatusBar().removeStatusItem_(item)
        except Exception:
            pass
        _state.update({"item": None, "menu": None, "target": None,
                       "on_click": None})
