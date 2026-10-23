from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import ClassVar

from typing import Any

from ..core.base import Definition

ROLE_NAME = re.compile(r"^[a-z][a-z0-9_:-]{0,62}$")
PERMISSION = re.compile(r"^[A-Za-z][A-Za-z0-9_.:*-]{0,80}$")


@dataclass
class Role(Definition):
    """A role and what it may do. Policies refer to roles with ``P.role("teacher")`` and to permissions with ``P.permission("grades.write")``.

        Role("teacher", permissions=["grades.write", "attendance.write"], description="Teaching staff")

    The permissions are names you choose; nothing is enforced by a permission until a policy checks it. Giving a role to a person is done
    in Accounts (Studio → Users, or the users API), not here.
    """

    kind: ClassVar[str] = "roles"
    name: str
    permissions: list[str] = field(default_factory=list)
    description: str = ""

    def body(self, *, resolve: bool = True) -> dict[str, Any]:
        # The server returns permissions sorted, so send them sorted: order is not a difference.
        return {"name": self.name, "description": self.description, "permissions": sorted(self.permissions)}

    def problems(self) -> list[str]:
        out = []
        if not ROLE_NAME.match(self.name):
            out.append(f"role {self.name!r}: lowercase letters, digits, _ : and -, starting with a letter")
        for permission in self.permissions:
            if not PERMISSION.match(permission):
                out.append(f"permission {permission!r}: letters, digits and . _ : * -, starting with a letter")
        if len(set(self.permissions)) != len(self.permissions):
            out.append("a permission is listed twice")
        return out
