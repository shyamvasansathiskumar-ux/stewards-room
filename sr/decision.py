"""Read one stewards' decision from its text, and quote everything.

The FIA prints every decision as the same labelled table:
No / Driver, Competitor, Time, Session, Fact, Infringement, Decision, Reason.
So the fields don't need guessing. This module finds each label, takes the text
after it, and records exactly where in the source that text sits. A field that
isn't in the text comes back as None. Nothing is ever filled in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

LABELS = ["No / Driver", "Competitor", "Time", "Session", "Fact",
          "Infringement", "Decision", "Reason"]
KEYS = {"No / Driver": "driver", "Competitor": "competitor", "Time": "time",
        "Session": "session", "Fact": "fact", "Infringement": "infringement",
        "Decision": "decision", "Reason": "reason"}

# Where the table ends: the FIA's standard footer and signature block.
_END = re.compile(r"(Competitors are reminded|Decisions of the Stewards are taken"
                  r"|The Stewards\s*\n\s*\w+ \w+\s*$)", re.M)
# A label sits at the left edge of the table (a little indent at most), followed by a gap of
# two or more spaces, a colon, or the end of the line. Wrapped value lines are indented far
# deeper, so a Reason line that happens to start with "Time and again" is not a label.
_LABEL = re.compile(r"^[ \t]{0,6}(" + "|".join(re.escape(l) for l in LABELS) + r")(?:[ \t]{2,}|[ \t]*:[ \t]*|[ \t]*$)",
                    re.M)
_HEADER_DATE = re.compile(r"^[ \t]{0,6}Date[ \t]{2,}(\d{1,2} [A-Z][a-z]+ \d{4})", re.M)
_MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July",
                                         "August", "September", "October", "November", "December"], 1)}


@dataclass
class Quote:
    text: str
    start: int   # character offsets into the source text
    end: int


@dataclass
class Penalty:
    kind: str                  # time | drive_through | stop_go | grid | pit_lane_start |
                               # back_of_grid | reprimand | warning | fine | nfa | none |
                               # suspension | disqualified | lap_time_deleted | other
    seconds: int | None = None
    places: int | None = None
    euros: int | None = None
    converted_from: str | None = None   # "10 second time penalty converted to ..."


@dataclass
class Decision:
    fields: dict = field(default_factory=dict)       # key -> Quote | None
    penalties: list = field(default_factory=list)    # [Penalty]
    points: int = 0
    stated_total: int | None = None                  # FIA's own "(total of N ...)"
    article: str | None = None                       # e.g. "L-IV-2d"
    date: str | None = None                          # the decision's printed date, ISO
    car: int | None = None
    driver: str | None = None
    problems: list = field(default_factory=list)

    def quote(self, key):
        q = self.fields.get(key)
        return q.text if q else None

    def to_json(self):
        d = asdict(self)
        return d


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def parse(text: str) -> Decision:
    """Parse the text of one decision (from `pdftotext -layout` or a copy-paste)."""
    d = Decision()
    marks = [(m.group(1), m.start(), m.end()) for m in _LABEL.finditer(text)]
    # A label such as "Time" also appears in the letter header above the table
    # (From / To / Document / Date / Time). The table starts at "No / Driver".
    first = next((i for i, (lab, _, _) in enumerate(marks) if lab == "No / Driver"), None)
    if first is None:
        d.problems.append("no 'No / Driver' label: not a stewards' decision table")
        for k in KEYS.values():
            d.fields[k] = None
        return d
    # Labels must come in the table's own order; anything out of order is body text.
    ordered, last = [], -1
    for lab, a, b in marks[first:]:
        k = LABELS.index(lab)
        if k > last:
            ordered.append((lab, a, b))
            last = k
    marks = ordered
    hd = _HEADER_DATE.search(text, 0, marks[0][1])
    if hd:
        dd, mon, yy = hd.group(1).split()
        if mon in _MONTHS:
            d.date = f"{yy}-{_MONTHS[mon]:02d}-{int(dd):02d}"
    stop = _END.search(text, marks[-1][2])
    end_all = stop.start() if stop else len(text)
    seen = set()
    for i, (lab, _s, e) in enumerate(marks):
        key = KEYS[lab]
        if key in seen:          # the first occurrence wins; the rest is body text
            continue
        nxt = end_all
        for lab2, s2, _e2 in marks[i + 1:]:
            if KEYS[lab2] not in seen and lab2 != lab:
                nxt = s2
                break
        raw = text[e:nxt]
        val = _clean(raw)
        if val:
            lead = len(raw) - len(raw.lstrip())
            tail = len(raw.rstrip())
            d.fields[key] = Quote(val, e + lead, e + tail)
        seen.add(key)
    for k in KEYS.values():
        d.fields.setdefault(k, None)

    _who(d)
    _article(d)
    _penalties(d)
    return d


def _who(d: Decision):
    q = d.quote("driver")
    if not q:
        d.problems.append("no driver field")
        return
    m = re.match(r"(\d{1,2})\s*[-–]\s*(.+?)(?:\s*[,;&]\s*\d{1,2}\s*[-–].*)?$", q)
    if m:
        d.car, d.driver = int(m.group(1)), normalise_driver(m.group(2).strip())
        if re.search(r"[,;&]\s*\d{1,2}\s*[-–]", q):
            d.problems.append("more than one driver in one decision: only the first is recorded")
    else:
        d.problems.append(f"driver field not in 'N - Name' form: {q!r}")


_ART = re.compile(r"Appendix\s+([A-Z]),\s*Chapter\s+([IVX]+),\s*Article\s+(\d+(?:\.\d+)*)\s*([a-z])?\)?",
                  re.I)


def _article(d: Decision):
    q = d.quote("infringement")
    if not q:
        return
    m = _ART.search(q)
    if m:
        d.article = f"{m.group(1).upper()}-{m.group(2).upper()}-{m.group(3)}{(m.group(4) or '').lower()}"
        return
    m = re.search(r"Article\s+(\d+(?:\.\d+)*)\s*([a-z])?\)?\s+of\s+the\s+(?:FIA\s+)?(?:\d{4}\s+)?"
                  r"(?:Formula 1\s+)?(Sporting|Technical|International Sporting)", q, re.I)
    if m:
        book = {"sporting": "SR", "technical": "TR", "international sporting": "ISC"}[m.group(3).lower()]
        d.article = f"{book}-{m.group(1)}{(m.group(2) or '').lower()}"


_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
        "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20}

# The same person is sometimes printed two ways. Extend this as the register grows.
ALIASES = {"andrea kimi antonelli": "Kimi Antonelli"}


def normalise_driver(name: str) -> str:
    n = re.sub(r"\s+", " ", name).strip()
    return ALIASES.get(n.lower(), n)


def _n(s: str) -> int:
    s = s.lower()
    return _NUM[s] if s in _NUM else int(s)


def _penalties(d: Decision):
    q = d.quote("decision")
    if not q:
        d.problems.append("no decision field")
        return
    t = q.lower()
    n = r"(\d+|" + "|".join(_NUM) + r")"

    m = re.search(r"\b" + n + r"\s+penalty points?\s*\(total of\s*" + n + r"\b", t)
    if m:
        d.points, d.stated_total = _n(m.group(1)), _n(m.group(2))
    else:
        m = re.search(r"\b" + n + r"\s+penalty points?", t)
        if m:
            d.points = _n(m.group(1))
        if "total of" in t:
            d.problems.append("a points total is printed but wasn't read")

    conv = re.search(n + r"\s*-?\s*second time penalty converted to (.+?)(?:\.|$)", t)
    if conv:
        g = re.search(r"drop of\s+" + n + r"\s+grid", conv.group(2))
        d.penalties.append(Penalty("grid", places=_n(g.group(1)) if g else None,
                                   converted_from=f"{_n(conv.group(1))} second time penalty"))
    else:
        for m in re.finditer(r"\b" + n + r"\s*-?\s*seconds?\s+time penalty", t):
            d.penalties.append(Penalty("time", seconds=_n(m.group(1))))
        for m in re.finditer(r"time penalty of\s+" + n + r"\s+seconds?", t):
            d.penalties.append(Penalty("time", seconds=_n(m.group(1))))
        g = (re.search(r"drop of\s+" + n + r"\s+grid", t) or re.search(r"\b" + n + r"\s+grid place", t)
             or re.search(r"\b" + n + r"\s*-?\s*places?\s+grid", t))
        if g:
            d.penalties.append(Penalty("grid", places=_n(g.group(1))))
    if "drive through" in t or "drive-through" in t:
        d.penalties.append(Penalty("drive_through"))
    m = re.search(r"(\d+)\s*-?\s*second stop", t)
    if m:
        d.penalties.append(Penalty("stop_go", seconds=int(m.group(1))))
    if re.search(r"\bstart (?:the (?:race|sprint) )?from the pit ?lane\b|\bpit ?lane start\b", t):
        d.penalties.append(Penalty("pit_lane_start"))
    if "back of the grid" in t:
        d.penalties.append(Penalty("back_of_grid"))
    if "disqualif" in t:
        d.penalties.append(Penalty("disqualified"))
    # "€10,000 of which is suspended" is a suspended FINE, not a race ban.
    if re.search(r"suspen(?:ded|sion) from (?:the )?(?:next )?(?:race|competition|event)|"
                 r"suspension (?:for|of) (?:one|1|the next) (?:race|competition)", t):
        d.penalties.append(Penalty("suspension"))
    if "reprimand" in t:
        d.penalties.append(Penalty("reprimand"))
    if re.search(r"\bwarning\b", t):
        d.penalties.append(Penalty("warning"))
    m = re.search(r"(?:€|\beur(?:o|os)?\b)\s*(\d[\d,. ]*\d)|(\d[\d,. ]*\d)\s*(?:€|\beuros?\b)", q, re.I)
    if m and "fine" in t:
        raw = (m.group(1) or m.group(2)).replace(" ", "")
        raw = re.sub(r"[.,]\d{2}$", "", raw)                 # cents: "2,500.00"
        raw = raw.replace(",", "").replace(".", "")
        if raw.isdigit():
            d.penalties.append(Penalty("fine", euros=int(raw)))
    if "deleted" in t and "lap time" in t:
        d.penalties.append(Penalty("lap_time_deleted"))
    if "no further action" in t:
        d.penalties.append(Penalty("nfa"))
    if re.search(r"\bno penalty\b(?! points?)", t):
        d.penalties.append(Penalty("none"))
    if not d.penalties and not d.points:
        d.penalties.append(Penalty("other"))
        d.problems.append(f"decision not recognised: {q[:80]!r}")


def severity(d: Decision) -> float:
    """A rough single number for comparing outcomes, in 'seconds of race time'.
    It is a sorting aid, never shown as a verdict. Grid places count 1.5 s each
    (a convention, stated in the report, not an FIA figure)."""
    s = 0.0
    for p in d.penalties:
        if p.kind == "time":
            s += p.seconds or 0
        elif p.kind == "grid":
            s += 1.5 * (p.places or 0)
        elif p.kind == "drive_through":
            s += 20
        elif p.kind == "stop_go":
            s += 20 + (p.seconds or 0)
        elif p.kind in ("pit_lane_start", "back_of_grid"):
            s += 25
        elif p.kind in ("disqualified", "suspension"):
            s += 100
        elif p.kind == "reprimand":
            s += 0.5
    return s
