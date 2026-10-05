"""Minimal iCalendar (RFC 5545) writer for notice deadlines (stdlib only)."""
import os


def _esc(s):
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def _fold(line):
    """Fold to 75 octets per line without splitting a UTF-8 character."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur)
            cur = b""
        cur += b
    out.append(cur)
    return "\r\n ".join(x.decode("utf-8") for x in out)


def _utc(iso):
    """'2026-11-09T13:00:00.000+00:00' -> '20261109T130000Z' (ANAC gives UTC)."""
    return iso[:19].replace("-", "").replace(":", "") + "Z"


def write_calendar(path, *, name, description, stamp, events):
    """events: dicts with uid, start (ISO, UTC), summary, description, url."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ossian.cloud//bandi-feed//IT",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{_esc(name)}", f"X-WR-CALDESC:{_esc(description)}",
             "X-WR-TIMEZONE:Europe/Rome", "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
             "X-PUBLISHED-TTL:PT6H"]
    for ev in events:
        start = _utc(ev["start"])
        lines += ["BEGIN:VEVENT", f"UID:{ev['uid']}", f"DTSTAMP:{_utc(stamp)}",
                  f"DTSTART:{start}", f"DTEND:{start}",
                  f"SUMMARY:{_esc(ev['summary'])}", f"DESCRIPTION:{_esc(ev['description'])}",
                  f"URL:{ev['url']}", "TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    with open(path + ".tmp", "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(_fold(l) for l in lines) + "\r\n")
    os.replace(path + ".tmp", path)
