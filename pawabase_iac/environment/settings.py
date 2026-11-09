"""The environment's own configuration: who may sign up and how, the directory's policies, realtime, cross-origin rules, and open-ended settings your flows read.

    EnvironmentSettings(
        auth=Auth(signup_enabled=True, password_min_length=12, require_email_verification=True, mfa_enabled=True,
                  directory={"api_keys": {"enabled": True, "max_per_user": 5}, "mfa": {"require": "admins"}}),
        settings={"cors_origins": ["https://app.example.com"], "realtime": {"default_policy": "deny"}, "storefront_suffix": "shop.example.com"},
    )

There is one per environment. What you leave out is left alone (the server merges sections); a section you give is written. Open-ended `settings` keys are read by flows and
policies as `settings.<name>`.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from ..core.base import Definition, plain

#: ``section -> key -> (kind, low, high)``: the directory's policy sections, from the server (``identity/directory.py``).
DIRECTORY: dict[str, dict[str, tuple[str, Any, Any]]] = {
    "passwords": {"max_length": ("int", 16, 1024), "min_unique": ("int", 0, 32), "history": ("int", 0, 24), "max_age_days": ("int", 0, 3650), "forbid_personal": ("bool", None, None), "breach_check": ("bool", None, None)},
    "recovery": {"enabled": ("bool", None, None), "link_minutes": ("int", 5, 1440), "revoke_sessions": ("bool", None, None), "notify_change": ("bool", None, None)},
    "devices": {"track": ("bool", None, None), "notify_new": ("bool", None, None), "remember_days": ("int", 0, 365), "max_per_user": ("int", 0, 100)},
    "api_keys": {"enabled": ("bool", None, None), "max_per_user": ("int", 1, 100), "max_days": ("int", 0, 3650), "scoped": ("bool", None, None)},
    "avatars": {"enabled": ("bool", None, None), "bucket": ("bucket", None, None), "max_kb": ("int", 16, 10240)},
    "machines": {"enabled": ("bool", None, None), "max_machines": ("int", 1, 1000), "max_keys_per_machine": ("int", 1, 50), "max_days": ("int", 0, 3650), "token_minutes": ("int", 1, 60)},
    "mfa": {"totp": ("bool", None, None), "email": ("bool", None, None), "backup_codes": ("bool", None, None), "backup_code_count": ("int", 4, 20), "email_code_minutes": ("int", 5, 60),
            "require": ("choice", ("off", "all", "admins"), None), "grace_days": ("int", 0, 90)},
    "claims": {"mode": ("choice", ("all", "listed"), None)},
}

#: The sign-in and sign-up settings the server reads (``identity/environment.py``): name -> expected Python type(s).
AUTH_KEYS: dict[str, tuple[type, ...]] = {
    "signup_enabled": (bool,), "require_email_verification": (bool,), "password_policy": (str,), "password_min_length": (int,), "access_ttl": (int,), "refresh_ttl": (int,), "magic_link_enabled": (bool,),
    "email_code_enabled": (bool,), "anonymous_enabled": (bool,), "passkeys_enabled": (bool,), "passkey_rp_id": (str,), "mfa_enabled": (bool,), "site_url": (str,), "redirect_urls": (list,),
    "providers": (dict,), "default_roles": (list,), "emails": (dict,), "lockout_threshold": (int,), "lockout_minutes": (int,), "allowed_email_domains": (list,), "blocked_email_domains": (list,),
    "max_sessions": (int,), "branding": (dict,), "signup_form": (dict,), "legal": (dict,), "directory": (dict,), "password_rules": (dict,), "token_profiles": (list,),
}
PASSWORD_POLICIES = ("basic", "strong", "custom")
PLATFORM_SETTINGS = ("public_docs", "cors_origins", "ip_allowlist", "timezone", "currency", "locale", "description", "maintenance", "realtime")
CUSTOM_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def Auth(**settings: Any) -> dict[str, Any]:
    """Sign-in and sign-up settings, checked by name when you validate: `Auth(signup_enabled=False, mfa_enabled=True, directory={"api_keys": {"enabled": True}})`."""
    return settings


def directory_problems(directory: dict[str, Any]) -> list[str]:
    out = []
    for section, values in directory.items():
        spec = DIRECTORY.get(section)
        if spec is None:
            out.append(f"auth.directory.{section}: not a directory section (they are {', '.join(DIRECTORY)})")
            continue
        if not isinstance(values, dict):
            out.append(f"auth.directory.{section}: must be an object")
            continue
        for key, value in values.items():
            kind = spec.get(key)
            if kind is None:
                out.append(f"auth.directory.{section}.{key}: not a setting (they are {', '.join(spec)})")
            elif kind[0] == "bool" and not isinstance(value, bool):
                out.append(f"auth.directory.{section}.{key}: true or false")
            elif kind[0] == "int" and (isinstance(value, bool) or not isinstance(value, int) or not kind[1] <= value <= kind[2]):
                out.append(f"auth.directory.{section}.{key}: a whole number from {kind[1]} to {kind[2]}")
            elif kind[0] == "choice" and value not in kind[1]:
                out.append(f"auth.directory.{section}.{key}: one of {', '.join(kind[1])}")
    return out


class EnvironmentSettings(Definition):
    """The environment's auth, settings and infrastructure sections. Only one per environment (it is not created or deleted: it always exists)."""

    kind: ClassVar[str] = "environment"
    key_field: ClassVar[str] = "name"

    def __init__(self, *, auth: dict[str, Any] | None = None, settings: dict[str, Any] | None = None, infra: dict[str, Any] | None = None) -> None:
        self.name = "settings"
        self.auth, self.settings, self.infra = auth or {}, settings or {}, infra or {}
        self._register()

    def body(self, *, resolve: bool = True) -> dict[str, Any]:
        return {"name": self.name, **{name: plain(getattr(self, name), resolve=resolve) for name in ("auth", "settings", "infra") if getattr(self, name)}}

    def problems(self) -> list[str]:
        out = []
        for key, value in self.auth.items():
            kinds = AUTH_KEYS.get(key)
            if kinds is None:
                out.append(f"auth.{key}: not an auth setting (they are {', '.join(AUTH_KEYS)})")
            elif not isinstance(value, kinds) or (int in kinds and bool not in kinds and isinstance(value, bool)):
                out.append(f"auth.{key}: expected {' or '.join(t.__name__ for t in kinds)}")
        if self.auth.get("password_policy") not in (None, *PASSWORD_POLICIES):
            out.append(f"auth.password_policy: one of {', '.join(PASSWORD_POLICIES)}")
        if isinstance(self.auth.get("password_min_length"), int) and not 6 <= self.auth["password_min_length"] <= 128:
            out.append("auth.password_min_length: from 6 to 128")
        if isinstance(self.auth.get("directory"), dict):
            out += directory_problems(self.auth["directory"])
        for key in self.settings:
            if key not in PLATFORM_SETTINGS and not CUSTOM_KEY.match(key):
                out.append(f"settings.{key}: custom setting names use letters, digits and underscores")
        realtime = self.settings.get("realtime")
        if realtime is not None and not isinstance(realtime, dict):
            out.append("settings.realtime: an object with channels, default_policy and allow_client_publish")
        if not (self.auth or self.settings or self.infra):
            out.append("give auth=, settings= or infra=")
        return out
