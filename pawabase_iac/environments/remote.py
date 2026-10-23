"""A running Pawabase, reached through its Platform API."""

from __future__ import annotations

import json
from typing import Any

import httpx

from .base import ApiError, address


class RemoteEnvironment:
    """An environment of a running Pawabase, reached through its Platform API with a secret API key."""

    def __init__(self, url: str, environment: str, api_key: str, *, timeout: float = 30.0) -> None:
        self.name = environment
        self.url = url.rstrip("/")
        self.http = httpx.Client(base_url=self.url, headers={"apikey": api_key}, timeout=timeout)

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> RemoteEnvironment:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _base(self, kind: str) -> str:
        # User administration (and so roles) lives under /auth in the management API.
        return f"/platform/v1/envs/{self.name}/{'auth/roles' if kind == 'roles' else kind}"

    def _send(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        try:
            response = self.http.request(method, path, json=body)
        except httpx.HTTPError as error:
            raise ApiError(0, "unreachable", f"Could not reach {self.url}: {type(error).__name__}") from error
        if response.status_code >= 400:
            try:
                data = response.json()
            except ValueError:
                data = {}
            detail = data.get("detail") if isinstance(data, dict) else None
            message = (
                (data.get("message") if isinstance(data, dict) else None)
                or (detail if isinstance(detail, str) else None)
                or (json.dumps(detail) if detail else None)
                or response.text[:300]
                or f"HTTP {response.status_code}"
            )
            code = (data.get("error") or data.get("code") or "") if isinstance(data, dict) else ""
            raise ApiError(response.status_code, str(code), str(message), detail)
        return None if response.status_code == 204 or not response.content else response.json()

    def list(self, kind: str) -> list[dict[str, Any]]:
        data = self._send("GET", self._base(kind))
        return list(data.get("data", []) if isinstance(data, dict) else data or [])

    def create(self, kind: str, body: dict[str, Any]) -> dict[str, Any]:
        # Roles have one verb for both: PUT creates or replaces by name.
        if kind == "roles":
            return self._send("PUT", self._base(kind), body) or {}
        return self._send("POST", self._base(kind), body) or {}

    def replace(self, kind: str, live: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        if kind == "roles":
            return self._send("PUT", self._base(kind), body) or {}
        return self._send("PUT", f"{self._base(kind)}/{address(kind, live)}", body) or {}

    def migrate(self, resource: str) -> list[str]:
        """Create the table, or add the columns the definition gained. Never drops anything."""
        answer = self._send("POST", f"{self._base('resources')}/{resource}/migrate") or {}
        return list(answer.get("statements", []))

    def delete(self, kind: str, live: dict[str, Any]) -> None:
        self._send("DELETE", f"{self._base(kind)}/{address(kind, live)}")
