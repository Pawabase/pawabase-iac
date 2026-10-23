"""What a set of definitions would serve once deployed: the endpoints, schedules and hooks, worked out from the definitions alone."""

from __future__ import annotations

from typing import Any

from ..core.base import ORDER
from ..environments import live_key

_VERBS = {"list": ("GET", ""), "get": ("GET", "/{id}"), "create": ("POST", ""), "update": ("PATCH", "/{id}"), "delete": ("DELETE", "/{id}")}


def describe(rows: dict[str, list[dict[str, Any]]]) -> list[tuple[str, str]]:
    """``(what, detail)`` lines for everything the stored definitions serve."""
    out: list[tuple[str, str]] = []
    for row in rows.get("resources", []):
        for operation, settings in (row.get("operations") or {}).items():
            if (settings or {}).get("enabled"):
                verb, tail = _VERBS[operation]
                policy = (settings or {}).get("policy")
                out.append((f"{verb} /rest/v1/{row['name']}{tail}", f"resource {row['name']}.{operation}, policy {policy or 'none'}"))
    for row in rows.get("routes", []):
        if row.get("enabled", True):
            out.append((live_key("routes", row), f"runs flow {row.get('handler')}"))
    for row in rows.get("inbound-hooks", []):
        if row.get("enabled", True):
            out.append((f"POST /hooks/v1/{row['slug']}", f"{row.get('verification')} → {row.get('target_type')} {row.get('target')}"))
    for row in rows.get("buckets", []):
        out.append((f"/storage/v1/object/{row['name']}/*", "public" if row.get("public") else "private"))
    for row in rows.get("schedules", []):
        when = row.get("cron") or f"every {row.get('interval_seconds')}s"
        out.append((f"schedule {row['name']}", f"{when} → {row.get('target_type')} {row.get('target')}"))
    for row in rows.get("webhooks", []):
        out.append((f"webhook {row['name']}", f"{', '.join(row.get('events') or [])} → {row.get('url')}"))
    for row in rows.get("subscriptions", []):
        out.append((f"on {row['event']}", f"{row.get('target_type')} {row.get('target')}"))
    return out


def counts(rows: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    return {kind: len(rows.get(kind, [])) for kind in ORDER if rows.get(kind)}
