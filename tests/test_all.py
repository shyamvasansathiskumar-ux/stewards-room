import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from datetime import date

from sr.build import as_table, build, check
from sr.consistency import outcome, points_rate, spread
from sr.decision import parse, severity
from sr.points import Award, Clock, plus_months
from sr.register import Register
from sr.titles import family, parse_title

ROOT = os.path.join(os.path.dirname(__file__), "..")
GOLD = json.load(open(os.path.join(ROOT, "data", "gold.json"), encoding="utf-8"))["decisions"]

# A real decision as `pdftotext -layout` lays it out: header block, the table
# with wrapped lines, then the footer. Field values from 2025 Spanish GP Doc 40.
LAYOUT = """
  From           The Stewards                                     2025 SPANISH GRAND PRIX
  To             The Team Manager, Oracle Red Bull Racing
  Document       40
  Date           01 June 2025
  Time           18:03

  The Stewards, having received a report from the Race Director, heard from the driver and
  team representative, determine the following:

  No / Driver    1 - Max Verstappen
  Competitor     Oracle Red Bull Racing
  Time           16:33
  Session        Race
  Fact           Car 1 collided with Car 63 at turn 5.
  Infringement   Breach of Appendix L, Chapter IV, Article 2 d) of the FIA International
                 Sporting Code.
  Decision       10 second time penalty.
                 3 penalty points (total of 11 for the 12 month period).
  Reason         The Stewards reviewed positioning/marshalling system data, video, timing,
                 telemetry, and in-car video evidence.

  Competitors are reminded of the right to appeal certain decisions of the Stewards.
"""


class Parser(unittest.TestCase):
    def test_real_layout_with_wrapped_lines(self):
        d = parse(LAYOUT)
        self.assertEqual(d.car, 1)
        self.assertEqual(d.driver, "Max Verstappen")
        self.assertEqual(d.quote("time"), "16:33", "the header's Time is not the incident time")
        self.assertEqual(d.article, "L-IV-2d")
        self.assertEqual((d.points, d.stated_total), (3, 11))
        self.assertEqual([(p.kind, p.seconds) for p in d.penalties], [("time", 10)])
        self.assertEqual(d.quote("infringement"),
                         "Breach of Appendix L, Chapter IV, Article 2 d) of the FIA International Sporting Code.")
        self.assertNotIn("reminded", d.quote("reason"), "the footer is not part of the reason")

    def test_every_quote_points_back_into_the_source(self):
        d = parse(LAYOUT)
        for k, q in d.fields.items():
            if q is None:
                continue
            span = LAYOUT[q.start:q.end]
            self.assertEqual(" ".join(span.split()), q.text, k)

    def test_gold_set_parses_exactly(self):
        for g in GOLD:
            d = parse(as_table(g))
            ok = check(d, g["expect"])
            self.assertTrue(all(ok.values()), f"{g['url']}: {ok} {d.penalties}")

    def test_a_missing_field_stays_missing(self):
        g = next(x for x in GOLD if x["fact"] is None)        # 2025 Hungary, Doc 42 has no Fact
        d = parse(as_table(g))
        self.assertIsNone(d.fields["fact"])

    def test_not_a_decision(self):
        d = parse("Provisional Race Classification\n1 4 Lando Norris")
        self.assertTrue(d.problems)
        self.assertIsNone(d.car)

    def test_unknown_wording_is_reported_not_guessed(self):
        d = parse("No / Driver  4 - X\nDecision  Something new the parser hasn't seen\nReason  r")
        self.assertEqual(d.penalties[0].kind, "other")
        self.assertTrue(any("not recognised" in p for p in d.problems))

    def test_conversion_is_one_penalty_not_two(self):
        g = next(x for x in GOLD if "converted" in x["decision"])
        d = parse(as_table(g))
        self.assertEqual([(p.kind, p.places) for p in d.penalties], [("grid", 5)])
        self.assertEqual(d.penalties[0].converted_from, "10 second time penalty")

    def test_fine_reprimand_drive_through(self):
        d = parse("No / Driver  16 - C\nDecision  Reprimand (Driving). Fine of €5,000. Drive through penalty.\nReason  r")
        kinds = {p.kind: p for p in d.penalties}
        self.assertEqual(kinds["fine"].euros, 5000)
        self.assertIn("reprimand", kinds)
        self.assertIn("drive_through", kinds)
        self.assertGreater(severity(d), 20)

    def test_words_as_numbers(self):
        d = parse("No / Driver  4 - X\nDecision  Two penalty points (total of Five for the 12 month period).\nReason  r")
        self.assertEqual((d.points, d.stated_total), (2, 5))


@unittest.skipUnless(shutil.which("pdftotext"), "needs pdftotext")
class RealPdf(unittest.TestCase):
    def test_pdf_through_pdftotext(self):
        from sr.fetch import pdf_text
        pdf = Path(ROOT, "tests", "fixtures", "sheet.pdf").read_bytes()
        d = parse(pdf_text(pdf))
        self.assertEqual((d.car, d.article, d.points, d.stated_total), (1, "L-IV-2d", 3, 11))
        self.assertEqual(d.quote("time"), "16:33")
        self.assertFalse(d.problems)

    def test_fetch_refuses_other_hosts(self):
        from sr.fetch import get
        with self.assertRaises(ValueError):
            get("https://example.com/x.pdf")


class Titles(unittest.TestCase):
    def test_real_titles(self):
        t = parse_title("Doc 40 - Infringement - Car 1 - Causing a Collision (With Car 63 at T5)")
        self.assertEqual((t.doc, t.kind, t.cars), (40, "infringement", [1, 63]))
        t = parse_title("Doc 68 - Corrected Race - Infringement - Car 81 - Causing a collision with Car 12 in Turn 1")
        self.assertTrue(t.corrected)
        self.assertEqual(t.kind, "infringement")
        self.assertEqual(t.cars[0], 81)
        t = parse_title("Doc 25 - Summons - Pit Lane Incident between Cars 63 & 14")
        self.assertEqual((t.kind, t.cars), ("summons", [63, 14]))
        t = parse_title("Doc 26 – Infringement - Qualifying Deleted Lap Times – Double Yellow")
        self.assertEqual(t.kind, "infringement")
        self.assertEqual(t.cars, [])
        t = parse_title("Doc 43 - Infringement - Car 14 False start - Moving before signal")
        self.assertEqual(t.cars, [14])
        self.assertIn("False start", t.subject)

    def test_incorrect_is_not_corrected(self):
        # 'Incorrect starting position' (2025 Bahrain, Doc 43) and 'serve time penalty
        # correctly' (2026 Monaco, Doc 93) are not re-issued documents.
        self.assertFalse(parse_title("Doc 43 - Infringement - Car 4 - Incorrect starting position").corrected)
        self.assertFalse(parse_title("DOC 93 - Infringement - Car 63 - Failing to serve time penalty correctly").corrected)

    def test_families(self):
        self.assertEqual(family("Car 55 moved under braking and made contact with Car 14"), "collision")
        self.assertEqual(family("Alleged forcing another driver off of the track"), "forcing_off")
        self.assertEqual(family("Failure to slow under yellow flags"), "yellow_flag")
        self.assertEqual(family("Pit Lane Speeding"), "pit_lane")


class PointsClock(unittest.TestCase):
    def test_expiry_is_twelve_months(self):
        a = Award("Max Verstappen", date(2025, 6, 1), 3, "spain")
        self.assertEqual(a.expires, date(2026, 6, 1))
        c = Clock([a])
        self.assertEqual(c.total("Max Verstappen", date(2026, 5, 31)), 3)
        self.assertEqual(c.total("Max Verstappen", date(2026, 6, 1)), 0)

    def test_leap_day(self):
        self.assertEqual(plus_months(date(2024, 2, 29), 12), date(2025, 2, 28))

    def test_ban_at_twelve(self):
        c = Clock([Award("D", date(2025, 1, 1), 6, "a"), Award("D", date(2025, 6, 1), 4, "b"),
                   Award("D", date(2025, 12, 1), 2, "c")])
        self.assertEqual([b[3] for b in c.bans()], ["c"])
        self.assertEqual(c.headroom("D", date(2025, 12, 1)), 0)
        # the first award expires on 1 Jan 2026, so the same 2 points a month later wouldn't ban
        c2 = Clock([Award("D", date(2025, 1, 1), 6, "a"), Award("D", date(2025, 6, 1), 4, "b"),
                    Award("D", date(2026, 1, 1), 2, "c")])
        self.assertEqual(c2.bans(), [])

    def test_keyed_on_driver_not_number(self):
        c = Clock([Award("Max Verstappen", date(2025, 6, 1), 3, "car 1 in 2025"),
                   Award("Max Verstappen", date(2026, 3, 1), 2, "car 3 in 2026")])
        self.assertEqual(c.total("Max Verstappen", date(2026, 3, 1)), 5)

    def test_fia_arithmetic_is_checked(self):
        c = Clock([Award("Max Verstappen", date(2025, 6, 1), 3, "spain", stated_total=11)])
        dis = c.disagreements()
        self.assertEqual(dis[0]["missing_points"], 8, "our ledger lacks 8 earlier points")

    def test_impossible_values_refused(self):
        with self.assertRaises(ValueError):
            Clock([Award("D", date(2025, 1, 1), 13, "x")])


class Register_(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "r.jsonl")

    def test_seen_unchanged_replaced(self):
        r = Register(self.path)
        self.assertEqual(r.observe("u", b"%PDF one", now="t1"), "SEEN")
        self.assertEqual(r.observe("u", b"%PDF one", now="t2"), "UNCHANGED")
        self.assertEqual(r.observe("u", b"%PDF two", now="t3"), "REPLACED")
        r2 = Register(self.path)
        self.assertEqual(len(r2.replaced()), 1)
        self.assertIsNotNone(r2.replaced()[0]["previous_sha256"])
        self.assertIsNone(r2.verify())

    def test_edits_are_detected(self):
        r = Register(self.path)
        r.observe("a", b"1", now="t")
        r.observe("b", b"2", now="t")
        r.observe("c", b"3", now="t")
        lines = Path(self.path).read_text().splitlines()
        row = json.loads(lines[1])
        row["title"] = "quietly changed"
        lines[1] = json.dumps(row, sort_keys=True)
        Path(self.path).write_text("\n".join(lines) + "\n")
        self.assertEqual(Register(self.path).verify(), 2)

    def test_deleted_line_is_detected(self):
        r = Register(self.path)
        for u in "abc":
            r.observe(u, u.encode(), now="t")
        lines = Path(self.path).read_text().splitlines()
        Path(self.path).write_text("\n".join([lines[0], lines[2]]) + "\n")
        self.assertEqual(Register(self.path).verify(), 2)


class Consistency(unittest.TestCase):
    def recs(self):
        return [{"url": g["url"], "event": g["event"], "season": int(g["date"][:4]),
                 "decision": parse(as_table(g))} for g in GOLD]

    def test_2026_collisions_carry_no_points(self):
        pr = points_rate(self.recs())
        self.assertEqual(pr[2025]["with_points"], pr[2025]["penalised"])
        self.assertEqual(pr[2026]["with_points"], 0)
        self.assertTrue(pr[2026]["small"])

    def test_departure_from_the_standard_is_explained(self):
        sp = {(s["article"], s["season"]): s for s in spread(self.recs())}
        s = sp[("L-IV-2d", 2026)]
        self.assertEqual(s["usual"], "10s")
        ham = next(d for d in s["departures"] if d["driver"] == "Lewis Hamilton")
        self.assertTrue(ham["explained"])
        self.assertIn("rather than the standard", ham["because"])
        # Two Sprint collisions were found to be breaches and given nothing: listed.
        self.assertEqual(sum(1 for d in s["departures"] if d["outcome"] == "no penalty"), 2)

    def test_excerpt_only_means_unknown_not_unexplained(self):
        recs = self.recs()
        for r in recs:
            r["reason_complete"] = False
        sp = {(s["article"], s["season"]): s for s in spread(recs)}
        ver = next(d for d in sp[("L-IV-2d", 2025)]["departures"] if d["driver"] == "Max Verstappen")
        self.assertIsNone(ver["explained"])

    def test_outcome_labels(self):
        g = GOLD[0]
        self.assertEqual(outcome({"decision": parse(as_table(g))}), "10s + 3pts")


def T(**f):
    """A decision table with the given fields, laid out like pdftotext's output."""
    lab = {"driver": "No / Driver", "time": "Time", "session": "Session", "fact": "Fact",
           "infringement": "Infringement", "decision": "Decision", "reason": "Reason"}
    lines = ["Date           01 June 2025", ""]
    for k in ("driver", "time", "session", "fact", "infringement", "decision", "reason"):
        if k in f:
            v = f[k].split("\n")
            lines.append(f"{lab[k]:<15}{v[0]}")
            lines += [" " * 15 + x for x in v[1:]]
    return "\n".join(lines)


class Loopholes(unittest.TestCase):
    """Each test is a loophole found in review, kept so it can't come back."""

    def test_wrapped_line_starting_with_a_label_word_stays_in_its_field(self):
        d = parse(T(driver="4 - X", fact="Car 4 left the track.\nReason given was a lock-up.",
                    decision="Reprimand.", reason="Time and again the driver ran wide.\nNo advantage."))
        self.assertIn("Reason given", d.quote("fact"))
        self.assertTrue(d.quote("reason").startswith("Time and again"))
        self.assertIsNone(d.fields["time"])

    def test_decision_date_comes_from_the_document(self):
        self.assertEqual(parse(T(driver="4 - X", decision="Reprimand.")).date, "2025-06-01")

    def test_suspended_fine_is_not_a_race_ban(self):
        d = parse(T(driver="4 - X", decision="A fine of €20,000, €10,000 of which is suspended."))
        self.assertEqual([p.kind for p in d.penalties], ["fine"])
        self.assertEqual(d.penalties[0].euros, 20000)
        d = parse(T(driver="20 - K", decision="Suspended from the next Competition."))
        self.assertIn("suspension", [p.kind for p in d.penalties])

    def test_pit_lane_words_are_not_a_pit_lane_start(self):
        d = parse(T(driver="4 - X", decision="A fine of EUR 500 for speeding in the pit lane during the restart."))
        self.assertNotIn("pit_lane_start", [p.kind for p in d.penalties])
        d = parse(T(driver="4 - X", decision="Required to start the race from the pit lane."))
        self.assertIn("pit_lane_start", [p.kind for p in d.penalties])

    def test_no_penalty_points_is_not_no_penalty(self):
        d = parse(T(driver="4 - X", decision="5 second time penalty. No penalty points."))
        self.assertEqual([p.kind for p in d.penalties], ["time"])

    def test_wording_variants(self):
        for text, want in [("3 place grid penalty for the next race.", ("grid", 3)),
                           ("Five second time penalty.", ("time", 5)),
                           ("Time penalty of 10 seconds.", ("time", 10))]:
            d = parse(T(driver="4 - X", decision=text))
            p = d.penalties[0]
            self.assertEqual((p.kind, p.seconds if p.kind == "time" else p.places), want, text)
        d = parse(T(driver="4 - X", decision="2 penalty points (total of eleven for the 12 month period)."))
        self.assertEqual(d.stated_total, 11)

    def test_fine_with_cents(self):
        d = parse(T(driver="4 - X", decision="Fine of €2,500.00."))
        self.assertEqual(d.penalties[0].euros, 2500)

    def test_two_drivers_in_one_decision_is_flagged(self):
        d = parse(T(driver="23 - Alexander Albon, 77 - Valtteri Bottas", decision="No further action."))
        self.assertEqual((d.car, d.driver), (23, "Alexander Albon"))
        self.assertTrue(any("more than one driver" in p for p in d.problems))

    def test_same_driver_two_spellings(self):
        d = parse(T(driver="12 - Andrea Kimi Antonelli", decision="Reprimand."))
        self.assertEqual(d.driver, "Kimi Antonelli")

    def test_ban_when_two_awards_fall_on_the_same_day(self):
        c = Clock([Award("D", date(2025, 1, 1), 10, "a", order=1),
                   Award("D", date(2025, 5, 1), 2, "b", order=10), Award("D", date(2025, 5, 1), 2, "c", order=11)])
        self.assertEqual([b[3] for b in c.bans()], ["b"])

    def test_same_day_totals_follow_document_order(self):
        c = Clock([Award("D", date(2025, 5, 1), 2, "z-url", stated_total=4, order=12),
                   Award("D", date(2025, 5, 1), 2, "a-url", stated_total=2, order=11)])
        self.assertEqual(c.disagreements(), [])

    def test_boilerplate_guideline_mention_is_not_an_explanation(self):
        from sr.consistency import _EXPLAIN
        self.assertIsNone(_EXPLAIN.search("did not satisfy the requirements of the Driving Standards Guidelines"))
        self.assertIsNotNone(_EXPLAIN.search("rather than the standard 10-second Time Penalty"))

    def test_fetch_only_https_fia(self):
        from sr.fetch import _check
        for bad in ["http://www.fia.com/x.pdf", "https://fia.com.evil.example/x.pdf", "https://example.com/x.pdf"]:
            with self.assertRaises(ValueError):
                _check(bad)
        _check("https://www.fia.com/system/files/decision-document/x.pdf")

    def test_register_half_written_line_is_reported_not_fatal(self):
        path = os.path.join(tempfile.mkdtemp(), "r.jsonl")
        r = Register(path)
        r.observe("a", b"1", now="t")
        with open(path, "a") as f:
            f.write('{"seq": 2, "ev')                     # a crash mid-write
        r2 = Register(path)
        self.assertEqual(r2.verify(), 2)
        with self.assertRaises(RuntimeError):
            r2.observe("b", b"2", now="t")

    def test_register_two_writers_keep_both_lines(self):
        path = os.path.join(tempfile.mkdtemp(), "r.jsonl")
        a, b = Register(path), Register(path)            # two runs opened the file at the same time
        a.observe("x", b"1", now="t")
        b.observe("y", b"2", now="t")
        r = Register(path)
        self.assertEqual([l["url"] for l in r.lines], ["x", "y"])
        self.assertIsNone(r.verify())

    def test_a_reissued_copy_does_not_count_points_twice(self):
        root = tempfile.mkdtemp()
        for f in ("gold.json", "index-summary.json"):
            shutil.copy(os.path.join(ROOT, "data", f), root)
        g = next(x for x in GOLD if x["doc"] == 53 and "dutch" in x["url"])
        dec = parse(as_table(g))
        from dataclasses import asdict
        with open(os.path.join(root, "decisions-2025.jsonl"), "w") as f:
            f.write(json.dumps({"url": g["url"].replace(".pdf", "_0.pdf"), "season": 2025, "event": g["event"],
                                "title": "Doc 53 - Infringement - Car 12", "doc": 53, "published": "31.08.25 19:30",
                                "decision": asdict(dec)}) + "\n")
        r = build(root, os.path.join(root, "out.json"), today=date(2025, 9, 1))
        ant = next(c for c in r["clock"] if c["driver"] == "Kimi Antonelli")
        self.assertEqual(sum(a["points"] for a in ant["awards"]), 4, "the _0 copy was counted again")


class Build(unittest.TestCase):
    def test_report(self):
        out = os.path.join(tempfile.mkdtemp(), "report.json")
        r = build(os.path.join(ROOT, "data"), out, today=date(2026, 10, 21))
        self.assertEqual(r["parser_score"]["passed"], r["parser_score"]["checks"])
        vers = next(c for c in r["clock"] if c["driver"] == "Max Verstappen")
        self.assertEqual(vers["active_today"], 0, "the Spain 2025 points expired on 1 June 2026")
        self.assertEqual(vers["awards"][0]["expires"], "2026-06-01")
        self.assertFalse(any(d["problems"] for d in r["decisions"]))
        # Antonelli: Austria 2 (total 2), Netherlands 2 (total 4). The ledger agrees with the FIA.
        self.assertEqual(sum(1 for a in r["agreements"] if a["driver"] == "Kimi Antonelli"), 2)


if __name__ == "__main__":
    unittest.main()
