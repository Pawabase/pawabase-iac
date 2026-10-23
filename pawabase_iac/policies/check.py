"""What the server's policy validator would say about a condition, without asking it."""

from __future__ import annotations

import re
from typing import Any

BINARY = ("eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "contains", "starts_with", "ends_with", "matches")
SHORTHANDS = ("authenticated", "role", "permission", "owner", "service", "kind", "scope", "aal")
UNARY = ("exists", "truthy", "empty")
#: Built-in policy names every environment understands. ``role:admin`` / ``owner:user_id`` style references are parameterised forms of these.
PARAMETERISED = ("role", "permission", "owner", "scope", "kind")
BUILTIN_POLICIES = frozenset({"public", "authenticated", "service", "owner", "none", "deny", "mfa", *PARAMETERISED})


def condition_problems(condition: Any, path: str = "condition") -> list[str]:
    if isinstance(condition, bool):
        return []
    if not isinstance(condition, dict) or len(condition) != 1:
        return [f"{path}: a condition is true, false, or one operator"]
    ((op, arg),) = condition.items()
    if op in ("all", "any"):
        if not isinstance(arg, list) or not arg:
            return [f"{path}.{op}: needs a list of conditions"]
        return [p for i, c in enumerate(arg) for p in condition_problems(c, f"{path}.{op}[{i}]")]
    if op == "not":
        return condition_problems(arg, f"{path}.not")
    if op in BINARY:
        if not isinstance(arg, list) or len(arg) != 2:
            return [f"{path}.{op}: needs [left, right]"]
        if op == "matches" and isinstance(arg[1], str) and not arg[1].startswith("$"):
            try:
                re.compile(arg[1])
            except re.error as exc:
                return [f"{path}.matches: invalid pattern: {exc}"]
        return []
    if op in UNARY or op in SHORTHANDS:
        return []
    return [f"{path}: unknown operator {op!r}"]


def reference_problems(value: Any, path: str) -> list[str]:
    """A policy reference is a name (checked later against what exists), or an inline condition (checked here)."""
    return condition_problems(value, path) if isinstance(value, (dict, bool)) else []


def referenced_policies(value: Any) -> list[str]:
    """The named policies a reference uses: ``"owner"``, ``"role:admin"`` (the base name is ``role``), or names inside a condition."""
    if isinstance(value, str):
        return [value.split(":", 1)[0]] if value.split(":", 1)[0] in PARAMETERISED else [value]
    if isinstance(value, dict):
        out: list[str] = []
        if isinstance(value.get("policy"), str):
            out.append(value["policy"])
        for item in value.values():
            out += referenced_policies(item) if isinstance(item, (dict, list)) else []
        return out
    if isinstance(value, list):
        return [name for item in value for name in referenced_policies(item)]
    return []


def referenced_access(value: Any) -> tuple[set[str], set[str]]:
    """The roles and permissions a policy reference or condition checks: ``({"teacher"}, {"grades.write"})``."""
    roles: set[str] = set()
    permissions: set[str] = set()
    if isinstance(value, str):
        kind, _, name = value.partition(":")
        if name and kind == "role":
            roles.add(name)
        elif name and kind == "permission":
            permissions.add(name)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key == "role" and isinstance(item, str):
                roles.add(item)
            elif key == "permission" and isinstance(item, str):
                permissions.add(item)
            elif isinstance(item, (dict, list, str)):
                found_roles, found_permissions = referenced_access(item)
                roles |= found_roles
                permissions |= found_permissions
    elif isinstance(value, list):
        for item in value:
            found_roles, found_permissions = referenced_access(item)
            roles |= found_roles
            permissions |= found_permissions
    return roles, permissions
