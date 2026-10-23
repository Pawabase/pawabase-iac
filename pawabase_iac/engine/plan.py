"""Planning and applying: what would change, and making it so."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from ..core.base import ORDER, Definition
from ..environments import ApiError, Environment, live_key
from ..kinds import KINDS

Action = Literal["create", "update", "noop", "extra", "delete"]
Mode = Literal["merge", "override"]


@dataclass
class Change:
    action: Action
    kind: str
    key: str
    body: dict[str, Any] = field(default_factory=dict)
    live: dict[str, Any] | None = None
    #: For an update: the fields that differ, as ``{"field": (live, wanted)}``.
    diff: dict[str, tuple[Any, Any]] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"{self.kind}/{self.key}"


@dataclass
class Plan:
    mode: Mode
    changes: list[Change]

    def of(self, *actions: Action) -> list[Change]:
        return [c for c in self.changes if c.action in actions]

    @property
    def pending(self) -> list[Change]:
        return self.of("create", "update", "delete")

    def summary(self) -> dict[str, int]:
        return {a: len(self.of(a)) for a in ("create", "update", "delete", "noop", "extra")}


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def differences(live: Any, wanted: Any, path: str = "") -> list[tuple[str, Any, Any]]:
    """Where *wanted* is not covered by *live*. The server adds defaults and ids, so extra keys in *live* are not differences, and
    an empty value matches a missing one."""
    if isinstance(wanted, dict):
        if not isinstance(live, dict):
            return [] if _empty(wanted) and _empty(live) else [(path, live, wanted)]
        out: list[tuple[str, Any, Any]] = []
        for key, value in wanted.items():
            out += differences(live.get(key), value, f"{path}.{key}" if path else key)
        return out
    if isinstance(wanted, list):
        if not isinstance(live, list):
            return [] if _empty(wanted) and _empty(live) else [(path, live, wanted)]
        if len(live) != len(wanted):
            return [(path, live, wanted)]
        out = []
        for index, (a, b) in enumerate(zip(live, wanted, strict=True)):
            out += differences(a, b, f"{path}[{index}]")
        return out
    if _empty(wanted) and _empty(live):
        return []
    if isinstance(wanted, (int, float)) and isinstance(live, (int, float)) and not isinstance(wanted, bool):
        return [] if float(wanted) == float(live) else [(path, live, wanted)]
    return [] if live == wanted else [(path, live, wanted)]


def existing_names(env: Environment) -> dict[str, set[str]]:
    return {kind: {live_key(kind, row) for row in env.list(kind)} for kind in ORDER}


def build_plan(items: list[Definition], env: Environment, mode: Mode = "merge", *, force_secrets: bool = False) -> Plan:
    """Compare what the code defines with what the environment has."""
    live_by_kind = {kind: {live_key(kind, row): row for row in env.list(kind)} for kind in ORDER}
    changes: list[Change] = []
    wanted_keys: dict[str, set[str]] = {kind: set() for kind in ORDER}
    for kind in ORDER:
        for item in (i for i in items if i.kind == kind):
            wanted_keys[kind].add(item.key)
            shown = item.body(resolve=False)
            live = live_by_kind[kind].get(item.key)
            if live is None:
                changes.append(Change("create", kind, item.key, shown))
                continue
            hidden = set(KINDS[kind].write_only)
            derived = {k for k in KINDS[kind].derived if shown.get(k) is None}
            diff = {path: (a, b) for path, a, b in differences(live, {k: v for k, v in shown.items() if k not in hidden | derived})}
            if not diff and force_secrets:
                diff = {name: ("(hidden)", "(sent again)") for name in hidden if getattr(item, name, None) is not None}
            changes.append(Change("update" if diff else "noop", kind, item.key, shown, live, diff))
    for kind in reversed(ORDER):
        for key, live in live_by_kind[kind].items():
            if key not in wanted_keys[kind]:
                changes.append(Change("delete" if mode == "override" else "extra", kind, key, {}, live))
    return Plan(mode, changes)


@dataclass
class Outcome:
    change: Change
    ok: bool
    error: str = ""
    #: For a table: the statements the migration ran.
    statements: list[str] = field(default_factory=list)


def apply_plan(
    plan: Plan,
    items: list[Definition],
    env: Environment,
    on_step: Callable[[Outcome], None] | None = None,
    *,
    resolve: bool = True,
    migrate: bool = True,
) -> list[Outcome]:
    """Carry out a plan: creates and updates in dependency order, then deletes in reverse. Stops at the first refusal, because
    what comes after may depend on it."""
    bodies = {(i.kind, i.key): i for i in items}
    outcomes: list[Outcome] = []
    ordered = [c for c in plan.changes if c.action in ("create", "update")] + [c for c in plan.changes if c.action == "delete"]
    for change in ordered:
        try:
            if change.action == "create":
                env.create(change.kind, bodies[(change.kind, change.key)].body(resolve=resolve))
            elif change.action == "update":
                assert change.live is not None
                env.replace(change.kind, change.live, bodies[(change.kind, change.key)].body(resolve=resolve))
            else:
                assert change.live is not None
                env.delete(change.kind, change.live)
            outcome = Outcome(change, True)
            if migrate and change.kind == "resources" and change.action in ("create", "update"):
                outcome.statements = env.migrate(change.key)
        except (ApiError, LookupError) as error:
            outcome = Outcome(change, False, str(error))
        outcomes.append(outcome)
        if on_step is not None:
            on_step(outcome)
        if not outcome.ok:
            break
    return outcomes


def missing_env(items: list[Definition]) -> list[str]:
    """Names of environment variables the definitions read (``env("X")``) that are not set, so a deploy can refuse before sending anything."""
    missing: list[str] = []
    for item in items:
        try:
            item.body()
        except LookupError as error:
            name = str(error).split()[2] if str(error).startswith("environment variable") else str(error)
            if name not in missing:
                missing.append(name)
    return missing
