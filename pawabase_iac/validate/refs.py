"""Checking a project before anything is sent: each definition on its own, then the references between them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.base import Definition, ref_name
from ..flows.flow import Flow
from ..policies.check import BUILTIN_POLICIES, referenced_access, referenced_policies
from ..tables.fields import Index  # noqa: F401  (re-exported for convenience in error messages)


@dataclass(frozen=True)
class Problem:
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.where}: {self.message}"


#: Block settings that name another definition: ``(block key or "family.*", setting) -> kind``.
FLOW_REFERENCES: dict[tuple[str, str], str] = {
    ("resource.*", "resource"): "resources",
    ("trigger.resource", "resource"): "resources",
    ("storage.*", "bucket"): "buckets",
    ("flow.call", "flow"): "flows",
    ("queue.flow", "flow"): "flows",
    ("mail.send", "template"): "mail-templates",
    ("policy.check", "policy"): "policies",
    ("transform.map", "transformer"): "transformers",
    ("trigger.webhook", "hook"): "inbound-hooks",
}


def _known(items: list[Definition], existing: dict[str, set[str]] | None, kind: str) -> set[str]:
    return {i.key for i in items if i.kind == kind} | (existing or {}).get(kind, set())


def check(items: list[Definition], existing: dict[str, set[str]] | None = None) -> list[Problem]:
    """Every problem in *items*, in the order a person should fix them. An empty list means the project is valid.

    *existing* names what the environment already has, by kind: a reference to something not in your code is fine when a merge
    deploy will find it there.
    """
    problems: list[Problem] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        for message in item.problems():
            problems.append(Problem(item.label, message))
        marker = (item.kind, item.key)
        if marker in seen:
            problems.append(Problem(item.label, "defined twice"))
        seen.add(marker)

    defined_roles = {i.key: i for i in items if i.kind == "roles"}
    known_roles = set(defined_roles) | (existing or {}).get("roles", set())
    granted = {p for role in defined_roles.values() for p in getattr(role, "permissions", [])}
    #: Permissions can only be judged when every role is one this project defines; a role made elsewhere may grant more.
    judge_permissions = bool(defined_roles) and known_roles == set(defined_roles)
    known = {kind: _known(items, existing, kind) for kind in ("flows", "schemas", "transformers", "resources", "buckets", "mail-templates", "inbound-hooks")}
    known["policies"] = _known(items, existing, "policies") | BUILTIN_POLICIES

    def need(item: Definition, what: str, value: Any, kind: str) -> None:
        name = ref_name(value)
        if name and "{{" not in name and name not in known[kind]:
            options = ", ".join(sorted(known[kind])) or "none"
            problems.append(Problem(item.label, f"{what} {name!r} is not defined (defined: {options})"))

    for item in items:
        body = item.body(resolve=False)
        if defined_roles or known_roles:
            roles_used, permissions_used = referenced_access(body)
            if item.kind != "roles":
                for role in sorted(roles_used - known_roles - {"anon", "authenticated"}):
                    if defined_roles:
                        problems.append(Problem(item.label, f"role {role!r} is not defined (roles: {', '.join(sorted(known_roles)) or 'none'})"))
                if judge_permissions:
                    for permission in sorted(permissions_used - granted):
                        problems.append(Problem(item.label, f"permission {permission!r} is not granted by any role"))
        if item.kind == "resources":
            for operation, settings in (body.get("operations") or {}).items():
                for name in referenced_policies((settings or {}).get("policy")):
                    need(item, f"operations.{operation}.policy", name, "policies")
            if isinstance(body.get("transformer"), str):
                need(item, "transformer", body["transformer"], "transformers")
            for relation in body.get("relations") or []:
                need(item, f"relation {relation.get('name')!r} resource", relation.get("resource"), "resources")
            for spec in body.get("fields") or []:
                if spec.get("type") == "ref":
                    need(item, f"field {spec.get('name')!r} schema", spec.get("schema"), "schemas")
        elif item.kind == "buckets":
            for key in ("read_policy", "write_policy", "list_policy", "update_policy", "delete_policy"):
                for name in referenced_policies(body.get(key)):
                    need(item, key, name, "policies")
        elif item.kind == "routes":
            if body.get("handler_type") == "flow":
                need(item, "handler flow", body.get("handler"), "flows")
            need(item, "input_schema", body.get("input_schema"), "schemas")
            need(item, "response_schema", body.get("response_schema"), "schemas")
            for name in referenced_policies(body.get("policy")):
                need(item, "policy", name, "policies")
            if isinstance(body.get("transformer"), str):
                need(item, "transformer", body["transformer"], "transformers")
        elif item.kind in ("subscriptions", "schedules", "inbound-hooks") and body.get("target_type") == "flow":
            need(item, "target flow", body.get("target"), "flows")
        elif item.kind == "flows" and isinstance(item, Flow):
            for node in item.graph().get("nodes", []):
                data = node.get("data") or {}
                key, config = data.get("block", ""), data.get("config") or {}
                for (pattern, setting), kind in FLOW_REFERENCES.items():
                    matches = key == pattern or (pattern.endswith(".*") and key.startswith(pattern[:-1]))
                    if matches and isinstance(config.get(setting), str):
                        if key == "resource.list" or True:
                            need(item, f"node {node['id']!r} ({key}) {setting}", config[setting], kind)
    return problems
