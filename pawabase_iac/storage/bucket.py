from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, ClassVar

from ..core.base import Definition, check_name, plain
from ..policies.check import reference_problems

POLICY_FIELDS = ("read_policy", "write_policy", "list_policy", "update_policy", "delete_policy")


@dataclass
class Bucket(Definition):
    """A storage bucket and who may do what in it.

        Bucket("avatars", public=True, accepts=["image/png", "image/jpeg"], max_bytes=2_000_000,
               write_policy=P.owner(), transforms={"enabled": True}, cache_max_age=86400)

    ``read_policy`` / ``write_policy`` are the defaults; ``list_policy``, ``update_policy`` and ``delete_policy`` override them per action.
    """

    kind: ClassVar[str] = "buckets"
    name: str
    description: str = ""
    public: bool = False
    read_policy: Any = None
    write_policy: Any = None
    accepts: list[str] = field(default_factory=list)
    max_bytes: int = 0
    signed_uploads: bool = True
    signed_downloads: bool = False
    list_policy: Any = None
    update_policy: Any = None
    delete_policy: Any = None
    transforms: dict[str, Any] = field(default_factory=dict)
    cache_max_age: int = 0

    def problems(self) -> list[str]:
        out = check_name(self.name, "bucket", re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$"))
        if self.max_bytes < 0:
            out.append("max_bytes cannot be negative")
        if not 0 <= self.cache_max_age <= 365 * 24 * 3600:
            out.append("cache_max_age is between 0 and a year")
        for pattern in self.accepts:
            if not re.match(r"^[a-z]+/([a-z0-9.+*-]+)$", pattern):
                out.append(f"accepts: {pattern!r} is not a content type like image/png or image/*")
        for key in POLICY_FIELDS:
            out += reference_problems(plain(getattr(self, key), resolve=False), key)
        return out
