# Stewards' Room

**Same offence, same penalty?** An open register of Formula 1 stewards' decisions. It reads the FIA's decision documents, quotes every field back to the PDF it came from, runs each driver's penalty-points clock, and lines up decisions made under the same rule so anyone can compare them.

It never says a decision was wrong. It shows decisions side by side, measures what can be counted, and says plainly what it can't tell.

**Site:** https://shyamvasansathiskumar-ux.github.io/stewards-room/

On the site you can:
- **Run the ban clock** for any driver in the register: drag through the dates, see which points are live and when they fall away, and add what-if points to see how close a ban is. Points the FIA counted but the register can't see yet are shown separately, never filled in.
- **Make the call** on 13 real incidents, worded exactly as the stewards printed them, then see their decision, their reason and the usual outcome under the same rule.
- **Search and open the register**: filter by season and kind, search any wording, and open a row to read every field as printed, with a link to the FIA PDF.

## What it found first (14 hand-checked decisions, hand-picked, small sample)

- **The 2026 points change shows up, so far.** Penalised collisions under Appendix L, Chapter IV, Article 2 d): 4 of 4 carried penalty points in 2025, 0 of 4 in 2026, matching the 2026 guidelines that keep points for dangerous, reckless or apparently deliberate driving. These 8 were picked by hand, so treat this as a pattern to test on the full fetch, not a result.
- **Departures get explained, sometimes.** 2026 Belgium: Hamilton got 5 s "rather than the standard 10-second Time Penalty", and the Reason says why. Two 2026 Singapore Sprint collisions were found to be breaches and given no penalty.
- **The FIA's arithmetic checks out where the history is complete.** Antonelli's printed totals (2, then 4) match the register. Verstappen's "total of 11" after Spain 2025 can't be checked yet: the register holds 3 of those points.
- **The clock must follow the driver, not the number.** Verstappen is Car 1 in 2025 documents and Car 3 in 2026.

## How it works

| Piece | What it does |
|---|---|
| `sr/decision.py` | Reads the FIA's labelled table (No / Driver, Competitor, Time, Session, Fact, Infringement, Decision, Reason), taking labels only at the table's left edge and in order. Every field keeps its exact character span in the source text, which is saved. A missing field stays missing; unfamiliar wording is flagged, never guessed. |
| `sr/titles.py` | Reads document titles (summons, decision, infringement; cars; "Corrected"). Titles route documents; only the PDF decides. |
| `sr/points.py` | The penalty-points clock: points count for 12 months, 12 means a one-race ban. Checks each printed "(total of N …)" against the register's own history. |
| `sr/register.py` | Append-only, hash-chained, file-locked record of every PDF fetched. A replaced document is recorded with both hashes (on republish, or every time with `--refresh`); an edited line is found by `verify()`; the head hash goes into the published report so a cut-off end can be spotted. |
| `sr/consistency.py` | Outcomes per article per season, the usual outcome, and every departure, marked explained / not explained / can't tell. |
| `sr/fetch.py` | Lists and downloads documents from https://www.fia.com only (redirects included), one request every 1.5 s, cached by URL hash. One bad document is skipped, not fatal. |
| `docs/interact.js` | The interactive parts of the site: the clock simulator, the incident game and the searchable register. Reads only `report.json`; all text is set as text, and links must point at fia.com. |
| `sr/build.py` | Builds `docs/report.json`. Merges re-issued copies of one decision (same event and document number), dates each decision from the document itself, and scores the parser's structured fields on the hand-checked set. |

## Run it

```bash
bash scripts/test.sh             # 44 tests; the PDF test needs pdftotext (brew install poppler)
bash scripts/update.sh 2026      # fetch the season from fia.com, read decisions, rebuild the data
python3 -m http.server -d docs   # view the site at http://localhost:8000
```

Python 3.10+, standard library only.

## Limits

- 14 hand-checked decisions so far; every group is a small sample.
- Only short Reason excerpts are stored, so many differences are "can't tell".
- Time, grid places and points aren't one currency. Outcomes are shown as printed.
- An LLM is not used. If one is added for odd layouts, it must quote its source span, and it is scored against the hand-checked set before it's trusted.

## Next

1. Run `update.sh` for 2025 and 2026 (about 450 decision PDFs).
2. Hand-check 50 decisions as the full gold set.
3. Track each driver's complete 12-month history, so every printed total can be reconciled.
4. Add summons-to-decision timing: how long from incident to verdict.

Data: FIA decision documents (fia.com). Not affiliated with or endorsed by the FIA, Formula 1 or any team. Formula 1 and F1 are trademarks of Formula One Licensing B.V. Non-commercial.

Shyam Kumar, CSE, Rajalakshmi Engineering College, 2026. MIT licence.
