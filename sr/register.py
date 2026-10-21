"""An append-only register of the FIA's documents, as they were when we saw them.

Every time a document is fetched, its bytes are hashed and a line is added to
a hash chain (the same design as Pathivu's audit log). That gives two things:

* If the FIA replaces a PDF at the same address, the next fetch sees a new
  hash and the register records a REPLACED event with both hashes. The old
  version is not lost from the record.
* If anyone edits the register file afterwards, `verify()` finds the first
  line that no longer matches its hash. Cutting lines off the END can only be
  caught by comparing `head` with a copy kept elsewhere: the build writes it
  into the published report for exactly that reason.

Lines are appended, never rewritten, under an exclusive lock, so two runs at
once can't lose each other's lines. A half-written last line (a crash mid-write)
is reported by `verify()` instead of stopping every later run.

The register stores hashes and metadata, never the PDF itself.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from datetime import datetime, timezone

GENESIS = "0" * 64


def _h(prev: str, body: dict) -> str:
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((prev + "|" + canon).encode("utf-8")).hexdigest()


class Register:
    def __init__(self, path: str):
        self.path = path
        self.lines: list[dict] = []
        self.unreadable: int | None = None      # line number of the first line that isn't JSON
        self._load()

    def _load(self):
        self.lines, self.unreadable = [], None
        if not os.path.exists(self.path):
            return
        with open(self.path, encoding="utf-8") as f:
            for n, raw in enumerate(f, 1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    self.lines.append(json.loads(raw))
                except json.JSONDecodeError:
                    self.unreadable = len(self.lines) + 1
                    break

    @property
    def head(self) -> str:
        return self.lines[-1]["hash"] if self.lines else GENESIS

    def latest(self, url: str):
        for line in reversed(self.lines):
            if line["url"] == url and line["event"] in ("SEEN", "REPLACED"):
                return line
        return None

    def observe(self, url: str, content: bytes, title: str = "", published: str = "",
                now: str | None = None) -> str:
        """Record a fetch. Returns 'SEEN', 'UNCHANGED' or 'REPLACED'."""
        digest = hashlib.sha256(content).hexdigest()
        with open(self.path, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)          # another run may have appended meanwhile
            try:
                self._load()
                if self.unreadable is not None:
                    raise RuntimeError(f"{self.path}: line {self.unreadable} is unreadable; "
                                       "repair the register before adding to it")
                prev = self.latest(url)
                if prev and prev["sha256"] == digest:
                    return "UNCHANGED"
                event = "REPLACED" if prev else "SEEN"
                body = {"seq": len(self.lines) + 1, "event": event, "url": url, "sha256": digest,
                        "bytes": len(content), "title": title, "published": published,
                        "at": now or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "previous_sha256": prev["sha256"] if prev else None}
                body["hash"] = _h(self.head, body)
                f.write(json.dumps(body, sort_keys=True, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
                self.lines.append(body)
                return event
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def verify(self):
        """Return None if the chain is intact, else the seq of the first bad line."""
        if self.unreadable is not None:
            return self.unreadable
        prev = GENESIS
        for i, line in enumerate(self.lines, 1):
            body = {k: v for k, v in line.items() if k != "hash"}
            if body.get("seq") != i or _h(prev, body) != line.get("hash"):
                return i
            prev = line["hash"]
        return None

    def replaced(self):
        return [l for l in self.lines if l["event"] == "REPLACED"]
