"""Draw a decision sheet as a real PDF (labels in one column, wrapped values in
another, like the FIA's), so the test can run it through the real pdftotext.
Run with: python3 tests/make_fixture.py  (needs reportlab)."""
import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROWS = [
    ("No / Driver", ["1 - Max Verstappen"]),
    ("Competitor", ["Oracle Red Bull Racing"]),
    ("Time", ["16:33"]),
    ("Session", ["Race"]),
    ("Fact", ["Car 1 collided with Car 63 at turn 5."]),
    ("Infringement", ["Breach of Appendix L, Chapter IV, Article 2 d) of the FIA International",
                      "Sporting Code."]),
    ("Decision", ["10 second time penalty.", "3 penalty points (total of 11 for the 12 month period)."]),
    ("Reason", ["The Stewards reviewed positioning/marshalling system data, video, timing,",
                "telemetry, and in-car video evidence."]),
]

out = os.path.join(os.path.dirname(__file__), "fixtures", "sheet.pdf")
c = canvas.Canvas(out, pagesize=A4)
y = 800
for lab, val in [("From", ["The Stewards"]), ("To", ["The Team Manager, Oracle Red Bull Racing"]),
                 ("Document", ["40"]), ("Date", ["01 June 2025"]), ("Time", ["18:03"])]:
    c.drawString(60, y, lab); c.drawString(160, y, val[0]); y -= 16
y -= 10
c.drawString(60, y, "The Stewards, having received a report from the Race Director, determine the following:")
y -= 26
for lab, vals in ROWS:
    c.setFont("Helvetica-Bold", 10); c.drawString(60, y, lab); c.setFont("Helvetica", 10)
    for v in vals:
        c.drawString(160, y, v); y -= 14
    y -= 6
c.drawString(60, y - 20, "Competitors are reminded of the right to appeal certain decisions of the Stewards.")
c.save()
print(out)
