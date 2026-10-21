"""The penalty-points clock.

The rule (ISC Appendix L, Chapter IV, as reported for 2025 and 2026): a driver
who reaches 12 penalty points within 12 months is suspended for the next
Competition, and each point stays active for 12 months from the offence.

Two things this module does that a points table on a news site doesn't:
1. It keys the clock on the DRIVER, not the car number. Numbers change: Max
   Verstappen raced as Car 1 in 2025 and as Car 3 in 2026.
2. It checks the FIA's own arithmetic. Each decision that gives points prints
   "(total of N for the 12 month period)". If our ledger, built from the
   decisions, disagrees with N, that is reported, never silently corrected.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

BAN_AT = 12


def plus_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    raise ValueError(d)


@dataclass(frozen=True)
class Award:
    driver: str
    on: date
    points: int
    source: str             # document URL or id
    stated_total: int | None = None
    order: int = 0          # the FIA's document number, to order awards made on the same day

    @property
    def expires(self) -> date:
        """First day the points no longer count."""
        return plus_months(self.on, 12)


class Clock:
    def __init__(self, awards=()):
        self.awards: list[Award] = []
        for a in awards:
            self.add(a)

    def add(self, a: Award):
        if a.points < 0 or a.points > BAN_AT:
            raise ValueError(f"impossible points value {a.points} in {a.source}")
        self.awards.append(a)
        self.awards.sort(key=lambda x: (x.on, x.order, x.source))

    def total(self, driver: str, on: date) -> int:
        return sum(a.points for a in self.awards
                   if a.driver == driver and a.on <= on < a.expires)

    def active(self, driver: str, on: date):
        return [a for a in self.awards if a.driver == driver and a.on <= on < a.expires]

    def next_expiry(self, driver: str, on: date):
        act = self.active(driver, on)
        return min((a.expires for a in act), default=None)

    def headroom(self, driver: str, on: date) -> int:
        """Points the driver can still take before the ban."""
        return BAN_AT - self.total(driver, on)

    def running(self):
        """Each award with the driver's total just after it, adding awards one at a time in
        document order. (Totals 'as of a day' would count every award made that day at once.)"""
        out = []
        for i, a in enumerate(self.awards):
            t = sum(b.points for b in self.awards[:i + 1]
                    if b.driver == a.driver and b.on <= a.on < b.expires)
            out.append((a, t))
        return out

    def bans(self):
        """Every moment someone reached the threshold, in order."""
        out = []
        for a, t in self.running():
            if t >= BAN_AT and t - a.points < BAN_AT:
                out.append((a.driver, a.on, t, a.source))
        return out

    def disagreements(self):
        """Decisions whose printed total differs from the ledger's total.

        A disagreement means one of three things, and the report says which it
        can't tell apart: (a) our ledger is missing an earlier decision, (b) a
        decision was changed later (a correction or a review), or (c) the
        printed figure is wrong. The first is the usual cause, so a ledger that
        starts mid-season will disagree until its history is complete.
        """
        out = []
        for a, ours in self.running():
            if a.stated_total is None:
                continue
            if ours != a.stated_total:
                out.append({"driver": a.driver, "on": a.on.isoformat(), "source": a.source,
                            "fia_says": a.stated_total, "ledger_says": ours,
                            "missing_points": a.stated_total - ours})
        return out

    def drivers(self):
        return sorted({a.driver for a in self.awards})
