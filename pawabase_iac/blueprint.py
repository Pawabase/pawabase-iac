"""Compiling a project into a blueprint bundle: a ``.zip`` with ``blueprint.yml`` and a file per concern, which any Pawabase can
install to build the whole app in a new environment (``POST /platform/v1/blueprints/install``).

    pawabase build                       # writes <project>.blueprint.zip
    pawabase build -o store.zip --name Store --environment shop

Everything you define is compiled: environment settings and sign-in (``EnvironmentSettings``), secrets, roles, tables, policies,
flows, routes, buckets, mail templates, events, connections, knowledge bases and agents. ``env("NAME")`` values become ``${NAME}``
variables, declared in ``blueprint.yml``, so no credential is written into the bundle; whoever installs it supplies them.

Parts the definition kinds don't model yet (AI providers and models, organization roles, realtime channels, alarms, the status
page, the mail kit, machines, API keys, sample data) are added with :class:`BlueprintPart`, written as the blueprint section::

    BlueprintPart("ai", {"providers": {"openai": {"kind": "openai", "key": env("OPENAI_API_KEY")}},
                         "models": {"chat": {"provider": "openai", "upstream": "gpt-4o-mini", "policy": "authenticated"}}})
    BlueprintPart("data", {"products": [{"title": "Lamp", "price": 25}]})

A project may also keep hand-written blueprint files in a ``blueprint/`` folder: they are copied into the bundle and included.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Any

import yaml

from .core.base import Definition, Env, current_registry

FORMAT_VERSION = 2

#: The blueprint section each kind is written under, and the file it goes in. Flows and mail templates get a file each.
SECTIONS: dict[str, tuple[str, str]] = {
    "secrets": ("secrets", "secrets.yml"),
    "roles": ("roles", "access.yml"),
    "schemas": ("schemas", "tables.yml"),
    "policies": ("policies", "access.yml"),
    "resources": ("tables", "tables.yml"),
    "flows": ("flows", "flows/{name}.yml"),
    "buckets": ("buckets", "storage.yml"),
    "mail-templates": ("mail_templates", "mail/{name}.yml"),
    "routes": ("routes", "api.yml"),
    "subscriptions": ("subscriptions", "events.yml"),
    "webhooks": ("webhooks", "events.yml"),
    "inbound-hooks": ("inbound_hooks", "events.yml"),
    "schedules": ("schedules", "events.yml"),
    "connections": ("connections", "ai.yml"),
    "knowledge-bases": ("knowledge_bases", "ai.yml"),
    "agents": ("agents", "ai.yml"),
}
#: Sections a BlueprintPart may add, and the file each goes in.
PART_FILES = {
    "ai": "ai.yml", "org_roles": "access.yml", "org_permissions": "access.yml", "realtime_channels": "realtime.yml",
    "status_page": "operations.yml", "alarms": "operations.yml", "mail": "mail/kit.yml", "machines": "access.yml",
    "keys": "access.yml", "data": "data.yml", "settings": "settings.yml", "auth": "auth.yml", "infra": "settings.yml",
}  # fmt: skip
ORDER = ["settings.yml", "auth.yml", "secrets.yml", "access.yml", "tables.yml", "ai.yml", "api.yml", "storage.yml", "events.yml", "realtime.yml", "operations.yml", "data.yml"]  # fmt: skip


class BlueprintPart:
    """A blueprint section given as-is, for parts the definition kinds don't model: ``BlueprintPart("ai", {...})``.

    Values may use ``env("NAME")``, compiled to a ``${NAME}`` variable like everywhere else.
    """

    def __init__(self, section: str, value: Any) -> None:
        if section not in PART_FILES:
            raise ValueError(f"BlueprintPart: {section!r} is not a section it can add (they are {', '.join(PART_FILES)})")
        self.section, self.value = section, value
        current_registry().parts.append(self)


class _Dumper(yaml.SafeDumper):
    pass


_Dumper.add_representer(str, lambda d, v: d.represent_scalar("tag:yaml.org,2002:str", v, style="|" if "\n" in v else None))


def _dump(value: Any) -> str:
    return yaml.dump(value, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=120)


def _variables(value: Any, found: set[str]) -> Any:
    """*value* with every ``env("NAME")`` as ``${NAME}``; the names are added to *found*."""
    if isinstance(value, Env):
        found.add(value.name)
        return "${" + value.name + "}"
    if isinstance(value, dict):
        return {k: _variables(v, found) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_variables(v, found) for v in value]
    return value


def _body(item: Definition, found: set[str]) -> dict[str, Any]:
    """The item's request body with ``env()`` values as variables (read through the item's own ``body()``)."""
    original = Env.resolve
    Env.resolve = lambda self: (found.add(self.name), "${" + self.name + "}")[1]  # type: ignore[method-assign]
    try:
        return item.body(resolve=True)
    finally:
        Env.resolve = original  # type: ignore[method-assign]


def _merge(into: dict[str, Any], section: str, value: Any) -> None:
    if section in into and isinstance(into[section], list) and isinstance(value, list):
        into[section].extend(value)
    elif section in into and isinstance(into[section], dict) and isinstance(value, dict):
        into[section] = {**into[section], **value}
    else:
        into[section] = value


def compile_bundle(
    items: list[Definition],
    parts: list[BlueprintPart] = (),  # type: ignore[assignment]
    *,
    name: str,
    description: str = "",
    version: str = "",
    environments: list[str] | None = None,
    extra_dir: Path | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """The bundle's bytes, and a summary (files, counts, variables)."""
    found: set[str] = set()
    files: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}

    for item in items:
        if item.kind == "environment":
            body = _body(item, found)
            for section in ("settings", "infra"):
                if body.get(section):
                    _merge(files.setdefault("settings.yml", {}), section, body[section])
            if body.get("auth"):
                _merge(files.setdefault("auth.yml", {}), "auth", body["auth"])
            continue
        section, path = SECTIONS[item.kind]
        body = _body(item, found)
        if item.kind == "secrets":
            entry = {k: v for k, v in body.items() if k != "name" and v not in (None, "")}
            _merge(files.setdefault(path, {}), section, {body["name"]: entry})
        else:
            target = path.format(name=re.sub(r"[^A-Za-z0-9_.-]", "_", str(item.key)))
            _merge(files.setdefault(target, {}), section, [body])
        counts[section] = counts.get(section, 0) + 1

    for part in parts:
        value = _variables(part.value, found)
        _merge(files.setdefault(PART_FILES[part.section], {}), part.section, value)
        counts[part.section] = counts.get(part.section, 0) + (len(value) if isinstance(value, (list, dict)) else 1)

    root: dict[str, Any] = {"blueprint": FORMAT_VERSION, "name": name}
    if description:
        root["description"] = description
    if version:
        root["version"] = version
    if environments:
        root["environments"] = environments
    if found:
        root["variables"] = {v: {"description": f"{v} (read from your environment by env())", "secret": True} for v in sorted(found)}
    includes = [p for p in ORDER if p in files]
    for folder in ("flows", "mail"):
        if any(p.startswith(f"{folder}/") for p in files):
            includes.append(f"{folder}/*.yml")

    out: dict[str, bytes] = {path: _dump(content).encode() for path, content in files.items()}
    if extra_dir is not None and extra_dir.is_dir():
        for file in sorted(extra_dir.rglob("*")):
            if file.is_file() and not file.name.startswith("."):
                out[f"extra/{file.relative_to(extra_dir).as_posix()}"] = file.read_bytes()
        if any(p.startswith("extra/") and p.endswith((".yml", ".yaml")) and p.count("/") == 1 for p in out):
            includes.append("extra/*.yml")
    if includes:
        root["include"] = includes
    out["blueprint.yml"] = ("# A Pawabase blueprint, compiled by pawabase-iac. Install it to build this app in a new environment.\n" + _dump(root)).encode()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(out):
            archive.writestr(path, out[path])
    return buffer.getvalue(), {"files": sorted(out), "counts": counts, "variables": sorted(found)}
