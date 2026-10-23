"""The ``pawabase`` command."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .. import project as config
from .._version import __version__
from ..core.base import ORDER, Definition
from ..engine import Plan, apply_plan, build_plan, existing_names, missing_env
from ..engine.surface import counts, describe
from ..environments import ApiError, EmulatedEnvironment, RemoteEnvironment
from ..validate import check
from .starter import STARTER

class CliError(Exception):
    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


class Out:
    def __init__(self) -> None:
        self.color = sys.stdout.isatty()

    def paint(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color else text

    def line(self, text: str = "") -> None:
        print(text)

    def ok(self, text: str) -> None:
        print(self.paint("✓ ", "32") + text)

    def warn(self, text: str) -> None:
        print(self.paint("! ", "33") + text, file=sys.stderr)

    def err(self, text: str) -> None:
        print(self.paint("✗ ", "31") + text, file=sys.stderr)


SIGNS = {"create": ("+", "32"), "update": ("~", "33"), "delete": ("-", "31"), "noop": ("=", "90"), "extra": ("?", "36")}


def show_plan(plan: Plan, out: Out, *, verbose: bool = False) -> None:
    for change in plan.changes:
        if change.action == "noop" and not verbose:
            continue
        sign, color = SIGNS[change.action]
        note = {"extra": "  (not in your code; left alone: use --mode override to remove)", "noop": "  (unchanged)"}.get(change.action, "")
        out.line(f"  {out.paint(sign, color)} {change.label}{note}")
        for path, (live, wanted) in change.diff.items():
            out.line(f"      {path}: {_short(live)} → {_short(wanted)}")
    s = plan.summary()
    out.line(
        f"\n{s['create']} to create, {s['update']} to change, {s['delete']} to delete, {s['noop']} unchanged"
        + (f", {s['extra']} not in code" if s["extra"] else "")
        + f"  [{plan.mode}]"
    )


def _short(value: Any) -> str:
    text = json.dumps(value, default=str) if not isinstance(value, str) else repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


def project(args: argparse.Namespace, out: Out) -> tuple[config.Settings, list[Definition]]:
    try:
        settings = config.load(Path.cwd(), environment=args.env, url=args.url, entry=args.entry)
        items = config.load_project(settings)
    except config.ConfigError as error:
        raise CliError(str(error)) from error
    return settings, items


def validated(items: list[Definition], out: Out, existing: dict[str, set[str]] | None = None) -> None:
    problems = check(items, existing)
    if problems:
        for problem in problems:
            out.err(str(problem))
        raise CliError(f"{len(problems)} problem{'s' if len(problems) != 1 else ''} found, so nothing was sent.")


def remote(settings: config.Settings, *, writing: bool) -> RemoteEnvironment:
    """The real environment. Reading it needs the project's API key; writing needs a secret key allowed to deploy."""
    if not settings.url:
        raise CliError("No Pawabase URL. Set `url` in pawabase.toml or PAWABASE_URL in the environment or .env.")
    if not settings.api_key:
        raise CliError(
            "No API key, so nothing can be pushed. Set PAWABASE_API_KEY (in .env or the environment).\n"
            "  Create one in Studio → API keys → New key → type Secret, preset “Deploy and configure”."
        )
    if writing and not settings.api_key.startswith("pb_sk"):
        raise CliError("Deploying needs a secret key (it starts with pb_sk). A publishable key cannot manage the environment.")
    return RemoteEnvironment(settings.url, settings.environment, settings.api_key)


def explain(error: ApiError) -> str:
    if error.status in (401, 403) and error.code == "scope_not_allowed":
        return (
            "This API key is not allowed to do that. A deploy key needs the “Deploy and configure” preset "
            "(resources, flows, secrets, buckets, webhooks, events)."
        )
    if error.status in (401, 403):
        return f"The API key was refused ({error.message}). Check PAWABASE_API_KEY and that it belongs to environment {error.details or ''}".rstrip()
    return str(error)


def cmd_init(args: argparse.Namespace, out: Out) -> int:
    root = Path.cwd()
    target = root / "pawabase.toml"
    if target.exists():
        raise CliError("pawabase.toml already exists here.")
    target.write_text('# Where this project deploys. The API key is not here: it belongs in .env (PAWABASE_API_KEY).\n'
                      'url = "http://localhost:8080"\nenvironment = "development"\nentry = "infra"\n')
    (root / "infra").mkdir(exist_ok=True)
    (root / "infra" / "app.py").write_text(STARTER)
    (root / ".env.example").write_text("PAWABASE_API_KEY=pb_sk_...\n")
    out.ok("Created pawabase.toml, infra/app.py and .env.example.")
    out.line("Next: pawabase validate · pawabase emulate · pawabase deploy")
    return 0


def cmd_validate(args: argparse.Namespace, out: Out) -> int:
    _, items = project(args, out)
    validated(items, out)
    out.ok(f"{len(items)} definitions, all valid.")
    return 0


def cmd_plan(args: argparse.Namespace, out: Out) -> int:
    settings, items = project(args, out)
    validated(items, out)  # cheap and offline: refuse before touching the network
    with remote(settings, writing=False) as env:
        try:
            validated(items, out, existing_names(env) if args.mode == "merge" else None)
            plan = build_plan(items, env, args.mode, force_secrets=args.force_secrets)
        except ApiError as error:
            raise CliError(explain(error)) from error
    out.line(f"Plan for {settings.environment} at {settings.url}:")
    show_plan(plan, out, verbose=args.verbose)
    if args.json:
        out.line(json.dumps({"summary": plan.summary(), "changes": [[c.action, c.label] for c in plan.changes]}))
    return 0


def cmd_deploy(args: argparse.Namespace, out: Out) -> int:
    settings, items = project(args, out)
    validated(items, out)
    unset = missing_env(items)
    if unset:
        raise CliError("These environment variables are read by your definitions but not set, so nothing was sent:\n  " + "\n  ".join(unset))
    with remote(settings, writing=True) as env:
        try:
            validated(items, out, existing_names(env) if args.mode == "merge" else None)
            plan = build_plan(items, env, args.mode, force_secrets=args.force_secrets)
        except ApiError as error:
            raise CliError(explain(error)) from error
        out.line(f"Deploying to {settings.environment} at {settings.url}:")
        show_plan(plan, out)
        if not plan.pending:
            out.ok("Nothing to do: the environment already matches your code.")
            return 0
        if args.dry_run:
            out.ok("Dry run: nothing was sent.")
            return 0
        deleting = plan.of("delete")
        if (settings.production or deleting) and not args.yes:
            if not sys.stdin.isatty():
                raise CliError("This changes " + ("production" if settings.production else "by deleting things") + ": pass --yes to go ahead without asking.", 2)
            what = f"{len(plan.pending)} changes" + (f", including {len(deleting)} deletions" if deleting else "")
            if input(f"Apply {what} to {settings.environment}? [y/N] ").strip().lower() not in ("y", "yes"):
                raise CliError("Cancelled.")
        try:
            outcomes = apply_plan(plan, items, env, migrate=not args.no_migrate, on_step=lambda o: out.line(f"  {'✓' if o.ok else '✗'} {o.change.action} {o.change.label}" + (f"  ({len(o.statements)} migration statement{'s' if len(o.statements) != 1 else ''})" if o.statements else "") + ("" if o.ok else f"\n      {o.error}")))
        except ApiError as error:
            raise CliError(explain(error)) from error
    failed = [o for o in outcomes if not o.ok]
    if failed:
        left = len(plan.pending) - len(outcomes)
        raise CliError(f"Stopped at {failed[0].change.label}: {failed[0].error}\n  {left} later change(s) were not attempted. Fix it and deploy again; what was applied stays.")
    out.ok(f"Deployed {len(outcomes)} change(s) to {settings.environment}.")
    return 0


def cmd_emulate(args: argparse.Namespace, out: Out) -> int:
    settings, items = project(args, out)
    state = settings.root / ".pawabase" / f"emulator-{settings.environment}.json"
    if args.reset and state.exists():
        state.unlink()
    env = EmulatedEnvironment(settings.environment, state)
    validated(items, out, existing_names(env) if args.mode == "merge" else None)
    plan = build_plan(items, env, args.mode, force_secrets=args.force_secrets)
    out.line(f"Emulating a deploy to {settings.environment} (nothing real is touched; no API key needed):")
    show_plan(plan, out)
    outcomes = apply_plan(plan, items, env, resolve=False, migrate=not args.no_migrate)
    failed = [o for o in outcomes if not o.ok]
    if failed:
        raise CliError(f"The emulated environment refused {failed[0].change.label}: {failed[0].error}")
    env.save()
    rows = {kind: env.list(kind) for kind in ORDER}
    out.line()
    out.line("The emulated environment would serve:")
    for what, detail in describe(rows):
        out.line(f"  {what:<44} {detail}")
    out.line()
    out.ok(f"Emulated environment now holds {sum(counts(rows).values())} definitions ({', '.join(f'{n} {k}' for k, n in counts(rows).items())}).")
    out.line(f"  State kept in {state.relative_to(settings.root)}; run again to see only what changed, or --reset to start empty.")
    if args.json:
        out.line(json.dumps({"summary": plan.summary(), "serves": [list(x) for x in describe(rows)]}))
    return 0


def cmd_whoami(args: argparse.Namespace, out: Out) -> int:
    settings = config.load(Path.cwd(), environment=args.env, url=args.url, entry=args.entry)
    out.line(f"url:         {settings.url or '(not set)'}")
    out.line(f"environment: {settings.environment}")
    out.line(f"entry:       {settings.entry}")
    out.line(f"api key:     {(settings.api_key[:8] + '…') if settings.api_key else '(not set)'}")
    if settings.url and settings.api_key:
        with remote(settings, writing=False) as env:
            try:
                env.list("resources")
            except ApiError as error:
                raise CliError(explain(error)) from error
        out.ok("The key works for this environment.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-e", "--env", help="environment name (default: pawabase.toml)")
    common.add_argument("--url", help="Pawabase URL (default: pawabase.toml / PAWABASE_URL)")
    common.add_argument("--entry", help="file or folder holding your definitions (default: infra)")
    common.add_argument("--json", action="store_true", help="also print a machine-readable summary")
    sync = argparse.ArgumentParser(add_help=False)
    sync.add_argument("--mode", choices=("merge", "override"), default="merge",
                      help="merge: add and change, leave other things alone (default). override: make the environment match your code exactly, deleting the rest")
    sync.add_argument("--force-secrets", action="store_true", help="send webhook and hook secrets again (they cannot be compared)")
    sync.add_argument("--no-migrate", action="store_true", help="do not create or alter tables after changing a table's definition")
    parser = argparse.ArgumentParser(prog="pawabase", description="Pawabase as code: define, validate, plan, emulate and deploy.")
    parser.add_argument("--version", action="version", version=f"pawabase-iac {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")
    sub.add_parser("init", help="start a project here")
    sub.add_parser("validate", parents=[common], help="check your definitions without contacting anything")
    p = sub.add_parser("plan", parents=[common, sync], help="show what a deploy would change (reads the environment, writes nothing)")
    p.add_argument("-v", "--verbose", action="store_true")
    p = sub.add_parser("deploy", parents=[common, sync], help="apply your definitions to the environment (needs a deploy API key)")
    p.add_argument("--dry-run", action="store_true", help="show the plan, send nothing")
    p.add_argument("-y", "--yes", action="store_true", help="do not ask (needed for production and for deletions when not interactive)")
    p = sub.add_parser("emulate", parents=[common, sync], help="run a deploy against a simulated environment: nothing real is touched")
    p.add_argument("--reset", action="store_true", help="start from an empty emulated environment")
    sub.add_parser("whoami", parents=[common], help="show the settings and test the API key")
    return parser


COMMANDS = {"init": cmd_init, "validate": cmd_validate, "plan": cmd_plan, "deploy": cmd_deploy, "emulate": cmd_emulate, "whoami": cmd_whoami}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = Out()
    try:
        return COMMANDS[args.command](args, out)
    except CliError as error:
        out.err(str(error))
        return error.code
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
