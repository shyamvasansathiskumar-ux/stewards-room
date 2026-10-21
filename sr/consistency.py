"""Same offence, same penalty?

This module never says a decision was wrong. It lines decisions up so a
reader can compare them, and it measures three things that can be counted:

1. Spread: for one article of the rules in one season, which outcomes were
   given and how often.
2. Explained departures: when the outcome differs from the most common one
   for that article, does the Reason say why (for example "rather than the
   standard 10-second Time Penalty")? An unexplained departure is the thing
   worth asking about.
3. The 2026 points change: from 2026 the guidelines say points are only for
   dangerous, reckless or apparently deliberate actions causing a collision,
   or unsportsmanlike behaviour. So we count how often a penalised collision
   carried points, before and after.

Small samples are labelled as small. A spread of three decisions is a
conversation starter, not a finding.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from .decision import severity

SMALL = 8   # below this many decisions, a group is marked "small sample"

# Wording that explains why THIS penalty differs from the usual one. A bare mention of
# the guidelines doesn't count: most Reasons cite them whatever the outcome.
_EXPLAIN = re.compile(r"rather than the standard|instead of the (?:usual|standard)|mitigat|aggravat|"
                      r"exceptional circumstances|more severe|less severe|harsher|lesser penalty|"
                      r"reduced (?:the )?penalty|increased (?:the )?penalty", re.I)


def outcome(rec) -> str:
    """A short, readable label for what was given, e.g. '10s + 3pts'."""
    bits = []
    for p in rec["decision"].penalties:
        if p.kind == "time":
            bits.append(f"{p.seconds}s")
        elif p.kind == "grid":
            bits.append(f"{p.places} grid" + (" (converted)" if p.converted_from else ""))
        elif p.kind in ("nfa", "none"):
            bits.append("no penalty")
        else:
            bits.append(p.kind.replace("_", " "))
    if rec["decision"].points:
        bits.append(f"{rec['decision'].points}pts")
    return " + ".join(bits) or "unknown"


def _base(rec) -> str:
    conv = next((p.converted_from for p in rec["decision"].penalties if p.converted_from), None)
    if conv:
        m = re.match(r"(\d+) second", conv)
        label = f"{m.group(1)}s" if m else conv
        return label + (f" + {rec['decision'].points}pts" if rec["decision"].points else "")
    return outcome(rec)


def _breach_found(rec) -> bool:
    inf = (rec["decision"].quote("infringement") or "").lower()
    return inf.startswith("breach")


def penalised(rec) -> bool:
    return any(p.kind not in ("nfa", "none", "warning", "other") for p in rec["decision"].penalties) \
        or rec["decision"].points > 0


def groups(records):
    g = defaultdict(list)
    for r in records:
        art = r["decision"].article or "unknown"
        g[(art, r["season"])].append(r)
    return g


def spread(records):
    out = []
    for (art, season), recs in sorted(groups(records).items()):
        c = Counter(outcome(r) for r in recs)
        # "Usual" is the most common penalty among decisions that found someone
        # at fault, counting a converted penalty as what it was converted from.
        base = Counter(_base(r) for r in recs if penalised(r)) or c
        mode = base.most_common(1)[0][0]
        departures = []
        for r in recs:
            o = outcome(r)
            if _base(r) == mode:
                continue
            # A cleared driver ("Alleged breach ... No further action") is not a
            # departure. A breach found and then left unpunished is.
            if not penalised(r) and not _breach_found(r):
                continue
            reason = r["decision"].quote("reason") or ""
            m = _EXPLAIN.search(reason)
            # explained: True (the Reason says why), False (the full Reason doesn't),
            # None (we only hold an excerpt, so we can't tell).
            explained = True if m else (False if r.get("reason_complete", True) else None)
            departures.append({"url": r["url"], "event": r["event"], "driver": r["decision"].driver,
                               "outcome": o, "usual": mode, "explained": explained,
                               "because": _sentence(reason, m) if m else None})
        out.append({"article": art, "season": season, "n": len(recs), "small": len(recs) < SMALL,
                    "outcomes": dict(c.most_common()), "usual": mode,
                    "departures": departures,
                    "severity_range": [min(severity(r["decision"]) for r in recs),
                                       max(severity(r["decision"]) for r in recs)]})
    return out


def _sentence(text, m):
    a = text.rfind(".", 0, m.start()) + 1
    b = text.find(".", m.end())
    s = text[a: b + 1 if b != -1 else len(text)].strip()
    return s[:220]


def points_rate(records, article="L-IV-2d"):
    """Of the penalised decisions under one article, how many carried points, per season."""
    by = defaultdict(lambda: [0, 0])
    for r in records:
        if r["decision"].article != article or not penalised(r):
            continue
        by[r["season"]][1] += 1
        if r["decision"].points > 0:
            by[r["season"]][0] += 1
    return {s: {"with_points": a, "penalised": b, "small": b < SMALL} for s, (a, b) in sorted(by.items())}
