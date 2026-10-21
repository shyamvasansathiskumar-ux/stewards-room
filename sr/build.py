"""Build docs/report.json, which the website reads.

    python3 -m sr.build

Sources, in order of trust:
1. data/gold.json: decisions whose fields were checked by hand against the PDF.
2. data/decisions-<season>.jsonl: decisions read by sr.fetch from the PDFs.
   One decision can sit at several addresses (a "Corrected" re-issue, a file
   uploaded again as ..._0.pdf). Records are matched on (event, document
   number): the gold version wins, then the most recently published one.

The parser score counts the STRUCTURED fields (car, article, points, printed
total, penalties) that the parser derives from the hand-checked text. It is
not a score on real PDF layouts: that needs the fetched text, and is reported
separately once data/text/ exists.
"""
from __future__ import annotations

import glob
import json
import os
from datetime import date, datetime, timezone

from . import consistency
from .decision import Decision, Penalty, Quote, parse
from .points import Award, Clock
from .titles import family

FIELDS = ["driver", "competitor", "time", "session", "fact", "infringement", "decision", "reason"]
LABEL = {"driver": "No / Driver", "competitor": "Competitor", "time": "Time", "session": "Session",
         "fact": "Fact", "infringement": "Infringement", "decision": "Decision", "reason": "Reason"}


def as_table(g: dict) -> str:
    """Lay hand-checked fields out the way the FIA prints them, so the gold set
    goes through the same parser as fetched documents."""
    lines = ["From The Stewards", "To The Team Manager", f"Document {g.get('doc', '')}",
             f"Date {g['date']}", "Time 00:00", "", "The Stewards, having received a report, determine:", ""]
    for k in FIELDS:
        if g.get(k) is not None:
            lines.append(f"{LABEL[k]:<16}{g[k]}")
    lines += ["", "Competitors are reminded of their right to appeal."]
    return "\n".join(lines)


def _from_json(d: dict) -> Decision:
    dec = Decision()
    dec.fields = {k: (Quote(**v) if v else None) for k, v in d["fields"].items()}
    dec.penalties = [Penalty(**p) for p in d["penalties"]]
    for k in ("points", "stated_total", "article", "car", "driver", "problems"):
        setattr(dec, k, d[k])
    return dec


def check(dec: Decision, expect: dict) -> dict:
    got = {"car": dec.car, "article": dec.article, "points": dec.points,
           "stated_total": dec.stated_total,
           "penalties": [[p.kind, p.seconds if p.kind == "time" else p.places] for p in dec.penalties]}
    return {k: got[k] == expect[k] for k in expect}


def load(root="data"):
    recs, score = [], []
    with open(os.path.join(root, "gold.json"), encoding="utf-8") as f:
        gold = json.load(f)["decisions"]
    gold_urls = set()
    for g in gold:
        dec = parse(as_table(g))
        ok = check(dec, g["expect"])
        score.append({"url": g["url"], "ok": ok})
        gold_urls.add(g["url"])
        recs.append({"url": g["url"], "event": g["event"], "season": int(g["date"][:4]), "doc": g.get("doc"),
                     "date": g["date"], "decision": dec, "gold": True, "reason_complete": False})
    gold_keys = {(r["event"], r["doc"]) for r in recs if r["doc"] is not None}
    fetched = {}
    for path in sorted(glob.glob(os.path.join(root, "decisions-*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if r["url"] in gold_urls:
                    continue
                dec = _from_json(r["decision"])
                iso = dec.date or _published(r["published"])
                if iso is None:
                    dec.problems.append(f"no usable date (published {r['published']!r}): left out of the points clock")
                key = (r["event"], r.get("doc")) if r.get("doc") is not None else ("url", r["url"])
                if key in gold_keys:
                    continue
                rec = {"url": r["url"], "event": r["event"], "season": r["season"], "doc": r.get("doc"),
                       "date": iso or f"{r['season']}-01-01", "dated": iso is not None,
                       "published": r["published"], "decision": dec, "gold": False}
                old = fetched.get(key)
                if old is None or _published_sort(rec["published"]) >= _published_sort(old["published"]):
                    fetched[key] = rec
    recs.extend(fetched.values())
    return recs, score


def _published(p: str):
    """'07.12.25 16:48' -> '2025-12-07'; anything else -> None (never a guessed date)."""
    import re
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{2})\b", p or "")
    return f"20{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _published_sort(p: str):
    import re
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{2}) (\d{2}):(\d{2})", p or "")
    return (m.group(3), m.group(2), m.group(1), m.group(4), m.group(5)) if m else ("",)


def build(root="data", out="docs/report.json", today: date | None = None):
    today = today or datetime.now(timezone.utc).date()
    recs, score = load(root)
    clock = Clock()
    for r in recs:
        d = r["decision"]
        if d.points and d.driver and r.get("dated", True):
            clock.add(Award(d.driver, date.fromisoformat(r["date"]), d.points, r["url"], d.stated_total,
                            order=r.get("doc") or 0))
    with open(os.path.join(root, "index-summary.json"), encoding="utf-8") as f:
        index_summary = json.load(f)
    checks = [v for s in score for v in s["ok"].values()]
    reg_path = os.path.join(root, "register.jsonl")
    register_head = None
    if os.path.exists(reg_path):
        from .register import Register
        rg = Register(reg_path)
        register_head = {"lines": len(rg.lines), "head": rg.head, "intact": rg.verify() is None}
    report = {
        "generated": today.isoformat(),
        "index": index_summary,
        "decisions": [{
            "url": r["url"], "event": r["event"], "season": r["season"], "date": r["date"],
            "car": r["decision"].car, "driver": r["decision"].driver,
            "session": r["decision"].quote("session"), "article": r["decision"].article,
            "family": family(r["decision"].quote("fact") or r["decision"].quote("infringement") or ""),
            "fact": r["decision"].quote("fact"), "decision": r["decision"].quote("decision"),
            "reason": r["decision"].quote("reason"), "outcome": consistency.outcome(r),
            "points": r["decision"].points, "stated_total": r["decision"].stated_total,
            "gold": r["gold"], "problems": r["decision"].problems,
        } for r in sorted(recs, key=lambda r: r["date"], reverse=True)],
        "spread": consistency.spread(recs),
        "points_rate": consistency.points_rate(recs),
        "clock": [{"driver": drv, "active_today": clock.total(drv, today),
                   "awards": [{"on": a.on.isoformat(), "points": a.points, "expires": a.expires.isoformat(),
                               "stated_total": a.stated_total, "source": a.source}
                              for a in clock.awards if a.driver == drv]}
                  for drv in clock.drivers()],
        "disagreements": clock.disagreements(),
        "agreements": [{"driver": a.driver, "on": a.on.isoformat(), "fia_says": a.stated_total,
                        "source": a.source} for a in clock.awards
                       if a.stated_total is not None and clock.total(a.driver, a.on) == a.stated_total],
        "register": register_head,
        "parser_score": {"checks": len(checks), "passed": sum(checks), "documents": len(score),
                         "failures": [{"url": s["url"], "field": k} for s in score
                                      for k, v in s["ok"].items() if not v]},
    }
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    return report


if __name__ == "__main__":
    r = build()
    ps = r["parser_score"]
    print(f"{len(r['decisions'])} decisions · parser {ps['passed']}/{ps['checks']} checks on "
          f"{ps['documents']} hand-checked documents · {len(r['disagreements'])} points totals to reconcile")
