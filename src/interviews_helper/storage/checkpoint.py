from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import RUN_DIR


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def task_fingerprint(spec: dict[str, Any]) -> str:
    payload = json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class RunCheckpoint:
    path: Path
    state: dict[str, Any]

    @classmethod
    def open(
        cls,
        spec: dict[str, Any],
        *,
        run_id: str | None = None,
        resume: bool = True,
        directory: Path = RUN_DIR,
    ) -> "RunCheckpoint":
        directory.mkdir(parents=True, exist_ok=True)
        fingerprint = task_fingerprint(spec)
        path: Path | None = directory / f"{run_id}.json" if run_id else None
        if path and path.exists():
            state = json.loads(path.read_text(encoding="utf-8"))
            if state.get("fingerprint") != fingerprint:
                raise ValueError(f"运行 {run_id} 的参数与当前任务不一致")
            return cls(path, state)
        if resume and not run_id:
            candidates: list[tuple[str, Path, dict[str, Any]]] = []
            for candidate in directory.glob("*.json"):
                try:
                    state = json.loads(candidate.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if state.get("fingerprint") == fingerprint and state.get("status") != "complete":
                    candidates.append((state.get("updated_at", ""), candidate, state))
            if candidates:
                _, path, state = max(candidates, key=lambda item: item[0])
                return cls(path, state)
        actual_id = run_id or f"{datetime.now():%Y%m%d-%H%M%S-%f}-{fingerprint[:8]}"
        path = directory / f"{actual_id}.json"
        state = {
            "version": 1,
            "run_id": actual_id,
            "fingerprint": fingerprint,
            "status": "running",
            "spec": spec,
            "started_at": _now(),
            "updated_at": _now(),
            "completed_items": [],
            "failures": {},
        }
        checkpoint = cls(path, state)
        checkpoint.save()
        return checkpoint

    @property
    def run_id(self) -> str:
        return str(self.state["run_id"])

    def is_done(self, key: str) -> bool:
        return key in self.state["completed_items"]

    def mark_done(self, key: str) -> None:
        if key not in self.state["completed_items"]:
            self.state["completed_items"].append(key)
        self.state["failures"].pop(key, None)
        self.state["status"] = "running"
        self.save()

    def mark_failed(self, key: str, error: BaseException | str) -> None:
        self.state["failures"][key] = str(error)[:1000]
        self.state["status"] = "running"
        self.save()

    def finish(self) -> None:
        self.state["status"] = "partial" if self.state["failures"] else "complete"
        self.state["finished_at"] = _now()
        self.save()

    def save(self) -> None:
        self.state["updated_at"] = _now()
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)
