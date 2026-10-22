"""World clock: four cities, daylight saving handled automatically.

Times come from the IANA time-zone database (zoneinfo, with the tzdata
package on Windows). If that is missing, the rules for the cities offered
here are built in, so the clocks are still right, summer and winter."""
import datetime as dt
import json
import os

from .. import config

DEFAULT = ["California", "Frankfurt", "India", "Shanghai"]

# name: (IANA zone, standard UTC offset in minutes, daylight-saving rule)
CITIES = {
    "California": ("America/Los_Angeles", -480, "us"),
    "Honolulu": ("Pacific/Honolulu", -600, None),
    "Denver": ("America/Denver", -420, "us"),
    "Chicago": ("America/Chicago", -360, "us"),
    "Mexico City": ("America/Mexico_City", -360, None),
    "New York": ("America/New_York", -300, "us"),
    "Toronto": ("America/Toronto", -300, "us"),
    "São Paulo": ("America/Sao_Paulo", -180, None),
    "Buenos Aires": ("America/Argentina/Buenos_Aires", -180, None),
    "London": ("Europe/London", 0, "eu"),
    "Lisbon": ("Europe/Lisbon", 0, "eu"),
    "Lagos": ("Africa/Lagos", 60, None),
    "Frankfurt": ("Europe/Berlin", 60, "eu"),
    "Paris": ("Europe/Paris", 60, "eu"),
    "Amsterdam": ("Europe/Amsterdam", 60, "eu"),
    "Madrid": ("Europe/Madrid", 60, "eu"),
    "Rome": ("Europe/Rome", 60, "eu"),
    "Zurich": ("Europe/Zurich", 60, "eu"),
    "Stockholm": ("Europe/Stockholm", 60, "eu"),
    "Warsaw": ("Europe/Warsaw", 60, "eu"),
    "Athens": ("Europe/Athens", 120, "eu"),
    "Helsinki": ("Europe/Helsinki", 120, "eu"),
    "Johannesburg": ("Africa/Johannesburg", 120, None),
    "Istanbul": ("Europe/Istanbul", 180, None),
    "Moscow": ("Europe/Moscow", 180, None),
    "Nairobi": ("Africa/Nairobi", 180, None),
    "Dubai": ("Asia/Dubai", 240, None),
    "Karachi": ("Asia/Karachi", 300, None),
    "India": ("Asia/Kolkata", 330, None),
    "Dhaka": ("Asia/Dhaka", 360, None),
    "Bangkok": ("Asia/Bangkok", 420, None),
    "Jakarta": ("Asia/Jakarta", 420, None),
    "Shanghai": ("Asia/Shanghai", 480, None),
    "Hong Kong": ("Asia/Hong_Kong", 480, None),
    "Singapore": ("Asia/Singapore", 480, None),
    "Taipei": ("Asia/Taipei", 480, None),
    "Seoul": ("Asia/Seoul", 540, None),
    "Tokyo": ("Asia/Tokyo", 540, None),
    "Sydney": ("Australia/Sydney", 600, "au"),
    "Melbourne": ("Australia/Melbourne", 600, "au"),
    "Auckland": ("Pacific/Auckland", 720, "nz"),
}


def _path():
    return os.path.join(config.data_dir(), "worldclock.json")


def chosen():
    try:
        with open(_path(), encoding="utf-8") as fh:
            names = json.load(fh)
        names = [n for n in names if n in CITIES][:4]
        if len(names) == 4:
            return names
    except (OSError, ValueError, TypeError):
        pass
    return list(DEFAULT)


def choose(slot, name):
    names = chosen()
    names[slot] = name
    tmp = _path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(names, fh, ensure_ascii=False)
    os.replace(tmp, _path())
    return names


# -- built-in daylight-saving rules (used only without tzdata) ------------

def _nth_sunday(year, month, n):
    first = dt.datetime(year, month, 1)
    first_sunday = first + dt.timedelta(days=(6 - first.weekday()) % 7)
    return first_sunday + dt.timedelta(weeks=n - 1)


def _last_sunday(year, month):
    nxt = dt.datetime(year + (month == 12), month % 12 + 1, 1)
    last = nxt - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() + 1) % 7)


def _in_dst(rule, utc, std):
    """Whether `utc` (naive, UTC) falls in summer time under `rule`."""
    y = utc.year
    if rule == "us":       # 2nd Sunday March 02:00 local -> 1st Sunday Nov
        start = _nth_sunday(y, 3, 2) + dt.timedelta(hours=2) \
            - dt.timedelta(minutes=std)
        end = _nth_sunday(y, 11, 1) + dt.timedelta(hours=2) \
            - dt.timedelta(minutes=std + 60)
        return start <= utc < end
    if rule == "eu":       # last Sunday March -> last Sunday October, 01:00 UTC
        start = _last_sunday(y, 3) + dt.timedelta(hours=1)
        end = _last_sunday(y, 10) + dt.timedelta(hours=1)
        return start <= utc < end
    if rule == "au":       # 1st Sunday Oct 02:00 -> 1st Sunday April 03:00
        end = _nth_sunday(y, 4, 1) + dt.timedelta(hours=3) \
            - dt.timedelta(minutes=std + 60)
        start = _nth_sunday(y, 10, 1) + dt.timedelta(hours=2) \
            - dt.timedelta(minutes=std)
        return utc < end or utc >= start
    if rule == "nz":       # last Sunday Sept 02:00 -> 1st Sunday April 03:00
        end = _nth_sunday(y, 4, 1) + dt.timedelta(hours=3) \
            - dt.timedelta(minutes=std + 60)
        start = _last_sunday(y, 9) + dt.timedelta(hours=2) \
            - dt.timedelta(minutes=std)
        return utc < end or utc >= start
    return False


def local_time(name, now_utc=None):
    """The time in that city now, as a naive datetime, and whether it is
    summer time there."""
    zone, std, rule = CITIES[name]
    now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        here = now_utc.astimezone(ZoneInfo(zone))
        return here.replace(tzinfo=None), bool(here.dst())
    except Exception:
        pass
    utc = now_utc.astimezone(dt.timezone.utc).replace(tzinfo=None)
    summer = _in_dst(rule, utc, std)
    return utc + dt.timedelta(minutes=std + (60 if summer else 0)), summer


def describe(name, now_utc=None):
    """('14:05', 'Thu', '+1 day' or '' or '−1 day') for the tiles."""
    now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
    there, _summer = local_time(name, now_utc)
    here = now_utc.astimezone().replace(tzinfo=None)
    days = (there.date() - here.date()).days
    rel = "" if days == 0 else ("Tomorrow" if days > 0 else "Yesterday")
    return there.strftime("%H:%M"), there.strftime("%a"), rel
