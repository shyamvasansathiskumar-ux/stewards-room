"""Read the FIA's document titles, e.g.
'Doc 40 - Infringement - Car 1 - Causing a Collision (With Car 63 at T5)'.

The title is the cheapest signal: it says what kind of document it is, which
car, and roughly what for, before anyone opens the PDF. It is NOT the decision:
an 'Infringement' title can still end in 'No penalty is applied' (2026
Singapore, Doc 61). Titles route documents; only the PDF text decides.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

KINDS = ("summons", "decision", "infringement", "offence")


@dataclass
class Title:
    doc: int | None
    kind: str                # summons | decision | infringement | offence | other
    cars: list               # car numbers named in the title, first is the subject
    team: str | None
    subject: str             # the offence wording as printed
    corrected: bool
    session: str | None      # Race | Sprint | Qualifying | ... when the title says so


_DOC = re.compile(r"^\s*doc\s*(\d+)\s*[-–]\s*", re.I)
_SESS = re.compile(r"\b(sprint qualifying|sprint|qualifying|race|free practice \d|fp\d|"
                   r"reconnaissance laps)\b", re.I)


def parse_title(t: str) -> Title:
    s = re.sub(r"\s+", " ", t).strip()
    m = _DOC.match(s)
    doc = int(m.group(1)) if m else None
    rest = s[m.end():] if m else s
    corrected = bool(re.search(r"\bcorrected\b", rest, re.I))
    rest_nc = re.sub(r"\(?\s*corrected\s*\)?\s*[-–]?\s*", "", rest, flags=re.I).strip(" -–")
    parts = [p.strip() for p in re.split(r"\s+[-–]\s+", rest_nc) if p.strip()]
    kind, session = "other", None
    # The kind is in the first part ('Infringement', 'Sprint Infringement'), or
    # in the second when a session comes first ('Corrected Race - Infringement').
    for i, part in enumerate(parts[:2]):
        head = part.lower()
        k = next((k for k in KINDS if k in head), None)
        if k:
            kind = k
            for piece in parts[:i + 1]:
                sm = _SESS.search(piece)
                if sm:
                    session = sm.group(1).title()
            parts = parts[i + 1:]
            break
    cars = [int(c) for c in re.findall(r"\bcars?\s+(\d{1,2})\b", rest_nc, re.I)]
    cars += [int(c) for c in re.findall(r"\bcars?\s+\d{1,2}\s*(?:&|and)\s*(\d{1,2})\b", rest_nc, re.I)]
    team = None
    subj_parts = []
    for p in parts:
        if re.fullmatch(r"car\s+\d{1,2}", p, re.I):
            continue
        cm = re.match(r"car\s+\d{1,2}\s+(.+)", p, re.I)     # 'Car 14 False start - ...'
        subj_parts.append(cm.group(1) if cm else p)
    if parts and not re.match(r"car\s+\d", parts[0], re.I) and kind in KINDS and not cars:
        team = parts[0] if len(parts) > 1 else None
        if team:
            subj_parts = subj_parts[1:]
    return Title(doc, kind, cars, team, " - ".join(subj_parts), corrected, session)


# Offence families, matched on the title or the Fact. Only used for grouping;
# the Infringement article is the authority when the PDF has been read.
FAMILIES = [
    ("collision", r"collision|collided|colliding|contact"),
    ("forcing_off", r"forc\w* .*off|off (?:the|of the) track.*forc"),
    ("leaving_track_advantage", r"leaving the track.*advantage|gaining an? (?:lasting )?advantage"),
    ("track_limits", r"track limits|leaving the track without a justifiable reason"),
    ("impeding", r"imped|hinder"),
    ("erratic_or_dangerous", r"erratic|dangerous|change of direction|moved under braking|unsafe condition|rejoining"),
    ("yellow_flag", r"yellow"),
    ("red_flag", r"red flag"),
    ("safety_car", r"safety car|sc2-sc1|vsc"),
    ("pit_lane", r"pit lane speed|speeding|unsafe release|pit lane incident|fast lane"),
    ("start", r"false start|moving before|starting position|practice start|moved prior"),
    ("race_director", r"race director"),
    ("technical", r"technical|plank|weight|deflection|pu element|power unit|parc ferme|parc fermé|drs"),
]


def family(text: str) -> str:
    t = (text or "").lower()
    for name, rx in FAMILIES:
        if re.search(rx, t):
            return name
    return "other"
