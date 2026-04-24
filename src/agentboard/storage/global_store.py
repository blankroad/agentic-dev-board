"""Tier 1/2 dual-write facade over ~/.agentboard/ (global) + optional project root.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 arch.md §"Architecture Overview".
  - Tier 1 mode: installed project, global mirror write-through alongside project-local truth.
  - Tier 2 mode: ambient capture-only to ~/.agentboard/.
"""

import fcntl
import json
from pathlib import Path


class GlobalStore:
    def __init__(self, project_root: Path | None = None) -> None:
        self.root = Path.home() / ".agentboard"
        self.root.mkdir(mode=0o700, exist_ok=True)
        # Content-key dedup for decisions.jsonl writes. Source is intentionally
        # EXCLUDED from the key so hook + MCP dual capture of the same physical
        # tool call lands as exactly 1 entry (goal_checklist #4). FM6 handles
        # user/project hook content differences at a different layer (learnings,
        # not decisions). Rebuild the seen-set from disk so dedup survives across
        # GlobalStore instances (hook process + MCP process).
        self._decision_keys: set[str] = set()
        decisions_path = self.root / "decisions.jsonl"
        if decisions_path.is_file():
            for line in decisions_path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = entry.get("_content_key")
                if key:
                    self._decision_keys.add(key)
        self.project_root = project_root

    def write_session_md(self, session_id: str, date: str, content: str) -> Path:
        target = self.root / "sessions" / date / session_id / "session.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return target

    def init_tier2_session(self, session_id: str, date: str) -> Path:
        target = self.root / "sessions" / date / session_id / "session.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch(exist_ok=True)
        return target

    def finalize_session(self, session_id: str, date: str) -> Path:
        target = self.root / "sessions" / date / session_id / "session.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch(exist_ok=True)
        with target.open("a") as f:
            f.write("\n---\nfinalized: true\n")
        return target

    def write_decision(
        self,
        decision: dict,
        *,
        source: str,
        session_id: str,
        tool_call_seq: int,
        tool_name: str,
        args_json: str,
        ts_bucket: int,
    ) -> bool:
        del source  # intentionally excluded from content key
        content_key = (
            f"{session_id}|{tool_call_seq}|{tool_name}|{args_json}|{ts_bucket}"
        )
        persisted = dict(decision)
        persisted["_content_key"] = content_key
        line = json.dumps(persisted) + "\n"

        # Acquire LOCK_EX across the read-check-append window so concurrent
        # writers cannot both see "key absent" and both append. Arch.md
        # edge_case #2 explicitly requires fcntl.flock(LOCK_EX).
        global_target = self.root / "decisions.jsonl"
        global_target.touch(exist_ok=True)
        with global_target.open("r+") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                # Re-scan under lock so our view of _content_keys is current.
                f.seek(0)
                live_keys = set()
                for fline in f:
                    if not fline.strip():
                        continue
                    try:
                        entry = json.loads(fline)
                    except json.JSONDecodeError:
                        continue
                    key = entry.get("_content_key")
                    if key:
                        live_keys.add(key)
                if content_key in live_keys:
                    return False
                f.seek(0, 2)  # end
                f.write(line)
                f.flush()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        # Refresh the in-memory cache so repeat calls on this instance short-circuit.
        self._decision_keys.add(content_key)

        # Tier 1 mode: mirror to project-local .agentboard/decisions.jsonl.
        if self.project_root is not None:
            mirror = self.project_root / ".agentboard" / "decisions.jsonl"
            mirror.parent.mkdir(parents=True, exist_ok=True)
            with mirror.open("a") as mf:
                fcntl.flock(mf.fileno(), fcntl.LOCK_EX)
                try:
                    mf.write(line)
                    mf.flush()
                finally:
                    fcntl.flock(mf.fileno(), fcntl.LOCK_UN)
        return True
