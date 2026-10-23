"""Settings: ``pawabase.toml`` says where and what; ``.env`` or the environment holds the API key, which is never written to a file you commit."""

from __future__ import annotations

import importlib
import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from ..core.base import Definition, collecting

PRODUCTION_NAMES = frozenset({"production", "prod", "live"})


class ConfigError(Exception):
    pass


@dataclass
class Settings:
    root: Path
    url: str
    environment: str
    entry: str
    api_key: str

    @property
    def production(self) -> bool:
        return self.environment.lower() in PRODUCTION_NAMES


def load_dotenv(root: Path) -> None:
    """Read ``.env`` into the process environment without overriding what is already set."""
    path = root / ".env"
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def find_root(start: Path) -> Path:
    for directory in (start, *start.parents):
        if (directory / "pawabase.toml").is_file():
            return directory
    return start


def load(start: Path, *, environment: str | None = None, url: str | None = None, entry: str | None = None) -> Settings:
    root = find_root(start)
    load_dotenv(root)
    data: dict = {}
    path = root / "pawabase.toml"
    if path.is_file():
        try:
            data = tomllib.loads(path.read_text())
        except tomllib.TOMLDecodeError as error:
            raise ConfigError(f"pawabase.toml is not valid TOML: {error}") from error
    return Settings(
        root=root,
        url=(url or os.environ.get("PAWABASE_URL") or data.get("url") or "").rstrip("/"),
        environment=environment or os.environ.get("PAWABASE_ENV") or data.get("environment") or "development",
        entry=entry or data.get("entry") or "infra",
        api_key=os.environ.get("PAWABASE_API_KEY", ""),
    )


def _module_names(settings: Settings) -> list[str]:
    """Dotted module names for the project's definition files, in a stable order. A folder is a package, so files can import each other."""
    target = settings.root / settings.entry
    if target.is_dir():
        files = sorted(p for p in target.rglob("*.py") if not p.name.startswith("_") and "__pycache__" not in p.parts)
        if not files:
            raise ConfigError(f"{settings.entry!r} has no .py files.")
        return [".".join(f.relative_to(settings.root).with_suffix("").parts) for f in files]
    for candidate in (target, target.with_suffix(".py")):
        if candidate.is_file():
            return [".".join(candidate.relative_to(settings.root).with_suffix("").parts)]
    raise ConfigError(f"No definitions found: expected a file or folder at {settings.entry!r} (set `entry` in pawabase.toml).")


def load_project(settings: Settings) -> list[Definition]:
    """Import the project's definition files and return everything they defined, in the order it was defined.

    The project root is put on ``sys.path`` and the files are imported as modules (``infra.tables``), so ``from infra.policies import mine``
    works and each file runs once however many others import it.
    """
    names = _module_names(settings)
    before = set(sys.modules)
    sys.path.insert(0, str(settings.root))
    importlib.invalidate_caches()
    try:
        with collecting() as registry:
            for name in names:
                try:
                    importlib.import_module(name)
                except ConfigError:
                    raise
                except Exception as error:
                    raise ConfigError(f"{name.replace('.', '/')}.py failed to import: {type(error).__name__}: {error}") from error
            return list(registry.items)
    finally:
        sys.path.remove(str(settings.root))
        for module in set(sys.modules) - before:  # so loading again runs the files again
            del sys.modules[module]
