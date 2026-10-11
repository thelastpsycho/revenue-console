"""Crash-safe BAR apply checkpoint.

A successful D-EDGE apply is recorded *after* the success banner. A subsequent
run with an identical planned set of chunks skips those chunks. A changed plan
requires an explicit reset so stale accomplishments cannot silently be reused -
except for unattended scheduled runs, which pass discard_stale=True: nobody is
there to press Reset, and a dead checkpoint would otherwise block every run.
That is safe because bar_last_applied.json only records confirmed applies, so
anything the interrupted run didn't confirm is still in the new plan.

Important: if the website accepts a change but Selenium loses its confirmation
before the checkpoint is saved, inspect the D-EDGE extranet before retrying.
"""
import hashlib
import json
import os
import tempfile

from ...infrastructure.paths import get_data_path


class BarCheckpoint:
    def __init__(self, plan, *, path=None, reset=False, dry_run=False, discard_stale=False):
        self.enabled = not dry_run
        self.path = path or get_data_path("bar_apply_checkpoint.json")
        canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"))
        self.signature = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.completed = set()
        self.resumed = False
        self.discarded_stale = False
        if not self.enabled:
            return
        if reset and os.path.exists(self.path):
            os.unlink(self.path)
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as handle:
                state = json.load(handle)
            if state.get("signature") != self.signature and discard_stale:
                os.unlink(self.path)
                self.discarded_stale = True
                return
            if state.get("signature") != self.signature:
                raise RuntimeError(
                    "An unfinished BAR run has a different date/room/price plan. "
                    "Review the D-EDGE changes before starting again; choose "
                    "Reset checkpoint only if you deliberately want a new run."
                )
            completed = state.get("completed", [])
            if not isinstance(completed, list):
                raise RuntimeError("BAR checkpoint is invalid; inspect it before resetting")
            self.completed = set(completed)
            self.resumed = True

    @staticmethod
    def key(chunk):
        return json.dumps(chunk, sort_keys=True, separators=(",", ":"))

    def contains(self, chunk):
        return self.enabled and self.key(chunk) in self.completed

    def mark(self, chunk):
        if not self.enabled:
            return
        self.completed.add(self.key(chunk))
        self._write()

    def _write(self):
        folder = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(folder, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".bar-checkpoint-", dir=folder)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                os.chmod(temporary, 0o600)
                json.dump(
                    {"version": 1, "signature": self.signature,
                     "completed": sorted(self.completed)},
                    handle, sort_keys=True, indent=2,
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def finish(self):
        if self.enabled and os.path.exists(self.path):
            os.unlink(self.path)
