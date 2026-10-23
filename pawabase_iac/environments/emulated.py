"""A made-up environment held in memory (and optionally in a file)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .base import ApiError, _kinds, live_key


class EmulatedEnvironment:
    """A made-up environment held in memory (and optionally in a file), for trying a deploy with nothing real at stake.

    It keeps what a real one keeps: each definition under its key, an id, write-only fields dropped, and the server's own
    refusals for the cases that can be told from the definitions alone (a name already taken).
    """

    def __init__(self, name: str = "emulated", path: Path | None = None) -> None:
        self.name = name
        self.path = path
        self.rows: dict[str, dict[str, dict[str, Any]]] = {kind: {} for kind in _kinds()}
        self.counter = 0
        if path is not None and path.is_file():
            data = json.loads(path.read_text())
            self.rows.update(data.get("rows", {}))
            self.counter = int(data.get("counter", 0))

    def save(self) -> None:
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"counter": self.counter, "rows": self.rows}, indent=2, sort_keys=True))

    def _store(self, kind: str, body: dict[str, Any], row_id: str) -> dict[str, Any]:
        hidden = _kinds()[kind].write_only
        row = {k: copy.deepcopy(v) for k, v in body.items() if k not in hidden}
        for name in hidden:
            if body.get(name):
                row[f"{name}_set"] = True
        row["id"] = row_id
        return row

    def list(self, kind: str) -> list[dict[str, Any]]:
        return [copy.deepcopy(r) for r in self.rows[kind].values()]

    def create(self, kind: str, body: dict[str, Any]) -> dict[str, Any]:
        key = live_key(kind, body)
        if key in self.rows[kind]:
            raise ApiError(409, "conflict", f"{kind[:-1] if kind.endswith('s') else kind} already exists")
        self.counter += 1
        row = self._store(kind, body, f"emu{self.counter:06d}")
        self.rows[kind][key] = row
        return copy.deepcopy(row)

    def replace(self, kind: str, live: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        old_key, new_key = live_key(kind, live), live_key(kind, body)
        if old_key not in self.rows[kind]:
            raise ApiError(404, "not_found", f"no {kind} entry {old_key!r}")
        if new_key != old_key:
            raise ApiError(422, "key_changed", "a definition cannot be renamed by replacing it")
        row = self._store(kind, body, self.rows[kind][old_key]["id"])
        self.rows[kind][old_key] = row
        return copy.deepcopy(row)

    def migrate(self, resource: str) -> list[str]:
        return [f"(emulated) create or alter table for {resource}"]

    def delete(self, kind: str, live: dict[str, Any]) -> None:
        if self.rows[kind].pop(live_key(kind, live), None) is None:
            raise ApiError(404, "not_found", "no such definition")
