"""Pinch to zoom on a trackpad.

Windows spares us: a precision touchpad turns a pinch into an ordinary
wheel event with ctrl held, which is the same thing a mouse sends, so
the binding that was already there covers it. Nothing in this module
runs on Windows.

macOS does not. A pinch there is a magnify event, a kind Tk 8.6 has no
name for and never carries to the script — so on a Mac laptop with no
mouse plugged in there was no way to zoom at all short of the keyboard.
It is read from AppKit instead, through the pyobjc that is already
installed for the recogniser.

**The handler must not touch Tk.** This is the whole reason this file is
shaped the way it is, and the first version of it crashed the app on the
first pinch — abort, on the main thread, with no Python traceback.

The event arrives while Tk's main loop is inside Tcl_DoOneEvent, which
means Tcl's own lock is already held by this very thread. Calling
anything on a widget from in there — even `after`, which is about as
small a call as Tkinter has — asks for that lock a second time. It is
not a recursive lock. Tcl panics, and a Tcl panic is abort(): no
exception to catch, no traceback, nothing in the log, just a crash
report saying Python quit unexpectedly.

So the handler does one thing: it appends a pair of numbers to a deque.
That touches no widget, takes no lock the run loop cares about, and
cannot raise. Whoever asked for the watch reads that deque from a timer
of their own, on the Tk side of the fence, where calling Tk is legal.

Two monitors, not one. The overlay is a borderless window and macOS
does not always consider this application the frontmost one while it is
up, so the local monitor (which fires only when it is) would miss half
the gestures on its own; the global one catches the rest. A global
monitor cannot swallow the event, which is the right behaviour anyway —
the pinch was aimed at the overlay, and the document underneath it is
not scrolling.

Every failure here is quiet and total: no AppKit, an older pyobjc, a
monitor the system refuses to install. The wheel and the keyboard still
zoom, so a machine where this does not work is no worse off than before
it existed.
"""
import sys

# NSEventTypeMagnify. Named constants for it are missing from some
# pyobjc builds, and the number has not moved since the gesture was
# introduced.
MAGNIFY = 30
MAGNIFY_MASK = 1 << MAGNIFY


def available():
    """Whether a pinch can be heard on this machine at all."""
    if sys.platform != "darwin":
        return False
    try:
        __import__("AppKit")
    except Exception:
        return False
    return True


def watch(sink):
    """Post each pinch to `sink`, and hand back a way to stop.

    `sink` takes one argument, a pair: how much wider the fingers are
    than they were, as a fraction — about 0.01 to 0.05 at a time,
    positive to enlarge, not a total — and the moment it happened, in
    seconds.

    `sink` is called from AppKit's run loop, so it must be a deque's or a
    list's `append` or something equally small. It must not touch Tk; see
    the note at the top of this file for what happens if it does.

    Always returns something callable, so the caller never has to ask
    whether the watch was actually set up.
    """
    if not available():
        return lambda: None
    try:
        from AppKit import NSEvent
    except Exception:
        return lambda: None

    def heard(event):
        try:
            sink((float(event.magnification()), float(event.timestamp())))
        except Exception:
            # One bad event must not tear the monitor down; the next one
            # is a fortieth of a second away.
            pass

    def local(event):
        heard(event)
        return event                    # passed on, not swallowed

    tokens = []
    for add, handler in (
            ("addLocalMonitorForEventsMatchingMask_handler_", local),
            ("addGlobalMonitorForEventsMatchingMask_handler_", heard)):
        try:
            token = getattr(NSEvent, add)(MAGNIFY_MASK, handler)
        except Exception:
            token = None
        if token is not None:
            tokens.append(token)

    def stop():
        while tokens:
            try:
                NSEvent.removeMonitor_(tokens.pop())
            except Exception:
                pass

    return stop
