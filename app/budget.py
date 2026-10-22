"""The time a snip may take, step by step, and one log line that says
whether it kept to it.

Speed is a limit every change is checked against, not something put right
after a slow snip is reported. On the laptops Squint is built for (8 GB,
a recent i5 or an Apple M-chip) a snip is read, translated and shown in
three seconds at most; the aim is at once. Each step has its own share, so
a log from any computer says straight away which step went over:

    budget     : read 420/800 | first words 780/1000 | done 2210/3000 | ok
    budget     : read 6011/800 OVER | first words 6744/1000 OVER | ...

The same limits are checked before every release (bench/gates.py), and
the offline engine is helped by an online one when it will not finish in
time (translator.HELP_AFTER, HELP_FROM).
"""

READ_MS = 800          # the snipped area read
FIRST_MS = 1000        # the first translated words on screen
DONE_MS = 3000         # the whole translation on screen
LAYOUT_MS = 300        # laying a translated page out


def line(read_ms, first_ms, done_ms):
    """The log line for one snip. `first_ms` None when nothing was shown
    before the end."""
    parts, over = [], []
    for name, value, limit in (("read", read_ms, READ_MS),
                               ("first words", first_ms, FIRST_MS),
                               ("done", done_ms, DONE_MS)):
        if value is None:
            continue
        mark = ""
        if value > limit:
            mark = " OVER"
            over.append(name)
        parts.append("%s %.0f/%d%s" % (name, value, limit, mark))
    parts.append("over: " + ", ".join(over) if over else "ok")
    return " | ".join(parts)
