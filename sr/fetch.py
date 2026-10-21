"""Fetch the FIA's decision documents. Run this on your own computer:

    python3 -m sr.fetch --season 2026            # list every document
    python3 -m sr.fetch --season 2026 --pdfs     # also download stewards' decisions and read them

It is polite on purpose: one request every 1.5 seconds, a clear User-Agent,
and PDFs are cached, so a second run only downloads what's new. Each PDF is
hashed into data/register.jsonl. A PDF is downloaded again when the FIA's
"Published on" time for it changes; to catch a replacement that keeps the old
time, run with --refresh (every PDF is downloaded and re-hashed).

Only https://www.fia.com is ever contacted, redirects included. One failed
document is reported and skipped; it doesn't stop the run.

Needs Python 3.10+ and `pdftotext` (poppler: `brew install poppler` on a Mac).
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from .decision import parse
from .register import Register
from .titles import parse_title

BASE = "https://www.fia.com"
SEASONS = {  # the FIA's own page ids
    2025: "/documents/championships/fia-formula-one-world-championship-14/season/season-2025-2071",
    2026: "/documents/championships/fia-formula-one-world-championship-14/season/season-2026-2072",
}
UA = "StewardsRoom/0.1 (non-commercial research; github.com/shyamvasansathiskumar-ux/stewards-room)"
DELAY = 1.5
ALLOWED_HOSTS = {"www.fia.com", "fia.com"}
MAX_PDF = 8 * 1024 * 1024
_last = [0.0]


def _check(url: str):
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or u.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"refusing to fetch {url!r}: only https://www.fia.com")


class _SameSite(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only if it stays on https://www.fia.com."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_SameSite)


def get(url: str) -> bytes:
    _check(url)
    wait = DELAY - (time.monotonic() - _last[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with _OPENER.open(req, timeout=30) as r:
        body = r.read(MAX_PDF + 1)
    _last[0] = time.monotonic()
    if len(body) > MAX_PDF:
        raise ValueError(f"{url} is larger than {MAX_PDF} bytes")
    return body


class _Page(HTMLParser):
    """Collects event options and PDF links from one FIA documents page."""

    def __init__(self):
        super().__init__()
        self.events, self.docs = [], []
        self._opt = None
        self._a = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "option" and "/event/" in (a.get("value") or ""):
            self._opt = [a["value"], ""]
        if tag == "a" and (a.get("href") or "").lower().endswith(".pdf"):
            self._a = [a["href"], ""]

    def handle_data(self, data):
        if self._opt is not None:
            self._opt[1] += data
        if self._a is not None:
            self._a[1] += data

    def handle_endtag(self, tag):
        if tag == "option" and self._opt is not None:
            self.events.append((self._opt[1].strip(), self._opt[0]))
            self._opt = None
        if tag == "a" and self._a is not None:
            href, text = self._a
            text = re.sub(r"\s+", " ", html.unescape(text)).strip()
            m = re.search(r"Published on ([0-9.]+ [0-9:]+)", text)
            title = text[:m.start()].strip() if m else text
            self.docs.append({"title": title, "published": m.group(1) if m else "",
                              "url": urllib.parse.urljoin(BASE, href)})
            self._a = None


def index(season: int):
    p = _Page()
    p.feed(get(BASE + SEASONS[season]).decode("utf-8", "replace"))
    out = []
    for name, path in p.events:
        ep = _Page()
        ep.feed(get(urllib.parse.urljoin(BASE, path)).decode("utf-8", "replace"))
        for d in ep.docs:
            d.update(season=season, event=name)
            out.append(d)
        print(f"  {name}: {len(ep.docs)} documents", file=sys.stderr)
    return out


def pdf_text(pdf: bytes) -> str:
    if not shutil.which("pdftotext"):
        raise SystemExit("pdftotext not found: install poppler (brew install poppler)")
    r = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", "-", "-"], input=pdf,
                       capture_output=True, timeout=60, check=True)
    return r.stdout.decode("utf-8", "replace")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True, choices=sorted(SEASONS))
    ap.add_argument("--pdfs", action="store_true", help="download and read stewards' decisions")
    ap.add_argument("--refresh", action="store_true",
                    help="download every PDF again, to catch documents the FIA replaced silently")
    ap.add_argument("--data", default="data")
    a = ap.parse_args(argv)
    os.makedirs(os.path.join(a.data, "pdf"), exist_ok=True)

    docs = index(a.season)
    with open(os.path.join(a.data, f"index-{a.season}.jsonl"), "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"{len(docs)} documents listed for {a.season}", file=sys.stderr)
    if not a.pdfs:
        return

    reg = Register(os.path.join(a.data, "register.jsonl"))
    out_path = os.path.join(a.data, f"decisions-{a.season}.jsonl")
    tmp_path = out_path + ".partial"
    n, skipped = 0, []
    with open(tmp_path, "w", encoding="utf-8") as out:
        for d in docs:
            t = parse_title(d["title"])
            if t.kind not in ("decision", "infringement", "offence") or not t.cars:
                continue
            try:
                n += _one(a, reg, d, t, out)
            except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as e:
                skipped.append(d["url"])
                print(f"  skipped ({type(e).__name__}: {e}): {d['title']}", file=sys.stderr)
    os.replace(tmp_path, out_path)          # the old file stays whole until the new one is complete
    bad = reg.verify()
    print(f"{n} decisions read, {len(skipped)} skipped; register "
          f"{'intact' if bad is None else f'BROKEN at line {bad}'}", file=sys.stderr)


def _one(a, reg, d, t, out) -> int:
    """Fetch (or reuse), hash, read and write one decision. Returns 1."""
    # Cache by a hash of the full address, so two documents can never share a file.
    name = hashlib.sha256(d["url"].encode("utf-8")).hexdigest()[:32] + ".pdf"
    cache = os.path.join(a.data, "pdf", name)
    seen = reg.latest(d["url"])
    stale = a.refresh or (seen is not None and seen.get("published") != d["published"])
    if os.path.exists(cache) and not stale:
        with open(cache, "rb") as f:
            pdf = f.read()
    else:
        pdf = get(d["url"])
        if not pdf.startswith(b"%PDF"):
            raise ValueError("not a PDF")
        with open(cache, "wb") as f:
            f.write(pdf)
    event = reg.observe(d["url"], pdf, d["title"], d["published"])
    if event == "REPLACED":
        print(f"  REPLACED by the FIA since last fetch: {d['title']}", file=sys.stderr)
    text = pdf_text(pdf)
    os.makedirs(os.path.join(a.data, "text"), exist_ok=True)
    with open(os.path.join(a.data, "text", name[:-4] + ".txt"), "w", encoding="utf-8") as f:
        f.write(text)                  # kept, so every quoted span can be checked later
    dec = parse(text)
    out.write(json.dumps({"url": d["url"], "season": a.season, "event": d["event"],
                          "title": d["title"], "doc": t.doc, "published": d["published"],
                          "text_file": name[:-4] + ".txt",
                          "decision": dec.to_json()}, ensure_ascii=False) + "\n")
    return 1


if __name__ == "__main__":
    main()
