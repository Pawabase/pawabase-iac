"""Where definitions are read and written: a real environment over HTTP, or an emulated one in memory.

Both speak the same four verbs, so the planner and the deployer never know which they have.
"""

from __future__ import annotations

from typing import Any, Protocol


def _kinds():
    from ..kinds import KINDS

    return KINDS


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details

    def __str__(self) -> str:
        return f"{self.message} ({self.code or self.status})"


def live_key(kind: str, row: dict[str, Any]) -> str:
    """The name a stored definition goes by, the same one :attr:`Definition.key` gives the code side."""
    if kind == "routes":
        return f"{row.get('method', 'POST')} {row.get('path', '')}"
    return str(row.get(_kinds()[kind].key_field, ""))


def address(kind: str, row: dict[str, Any]) -> str:
    """What identifies a stored definition in a URL (its id for routes, otherwise its key)."""
    return str(row["id"]) if kind == "routes" else live_key(kind, row)


class Environment(Protocol):
    name: str

    def list(self, kind: str) -> list[dict[str, Any]]: ...
    def create(self, kind: str, body: dict[str, Any]) -> dict[str, Any]: ...
    def replace(self, kind: str, live: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]: ...
    def delete(self, kind: str, live: dict[str, Any]) -> None: ...
    def migrate(self, resource: str) -> list[str]: ...


