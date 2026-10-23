from __future__ import annotations

import re
from typing import Any, Literal

from ..core.base import Definition, Env, plain, ref_name

VERIFICATIONS = ("none", "hmac-sha256", "hmac-sha512", "hmac-sha256-ts", "pawabase", "token")


class InboundHook(Definition):
    """A URL other services call, verified, that raises an event or runs a flow. Named by its slug.

        InboundHook("stripe", run=payments_flow, verification="hmac-sha256", secret=env("STRIPE_HOOK_SECRET"),
                    signature_header="stripe-signature")
        InboundHook("github", event="github.push", verification="token", secret=env("GH_HOOK_TOKEN"))
    """

    kind = "inbound-hooks"
    key_field = "slug"
    write_only = ("secret",)

    def __init__(
        self,
        slug: str,
        *,
        run: Any = None,
        event: str | None = None,
        verification: Literal["none", "hmac-sha256", "hmac-sha512", "hmac-sha256-ts", "pawabase", "token"] = "hmac-sha256",
        signature_header: str = "x-signature",
        secret: str | Env | None = None,
        name: str = "",
        description: str = "",
        enabled: bool = True,
    ) -> None:
        if (run is None) == (event is None):
            raise ValueError("an inbound hook either runs a flow (run=) or raises an event (event=), not both")
        self.slug, self.name, self.description, self.enabled = slug, name or slug, description, enabled  # the server names it after the slug
        self.verification, self.signature_header, self.secret = verification, signature_header, secret
        self.target_type = "flow" if run is not None else "event"
        self.target = ref_name(run) if run is not None else event
        self._register()

    def body(self, *, resolve: bool = True) -> dict[str, Any]:
        return {
            "slug": self.slug, "name": self.name, "description": self.description, "verification": self.verification,
            "signature_header": self.signature_header, "target_type": self.target_type, "target": self.target,
            "enabled": self.enabled, "secret": plain(self.secret, resolve=resolve),
        }  # fmt: skip

    def problems(self) -> list[str]:
        out = []
        if not re.match(r"^[a-z0-9][a-z0-9-]{1,62}$", self.slug):
            out.append(f"slug {self.slug!r}: lowercase letters, digits and hyphens, 2 to 63 characters")
        if self.verification not in VERIFICATIONS:
            out.append(f"verification is one of {', '.join(VERIFICATIONS)}")
        elif self.verification != "none" and self.secret is None:
            out.append(f"verification {self.verification!r} needs a secret (use env('NAME'))")
        if isinstance(self.secret, str) and len(self.secret) < 16:
            out.append("secret is at least 16 characters")
        return out
