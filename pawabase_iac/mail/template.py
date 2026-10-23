from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from ..core.base import Definition, check_name


def variable(name: str, description: str = "", sample: Any = "") -> dict[str, Any]:
    """A value the template reads, with a sample for previews: ``variable("order_number", sample="A-1042")``."""
    return {"name": name, "description": description, "sample": sample}


@dataclass
class MailTemplate(Definition):
    """An email template. ``{{ name }}`` in subject, html and text reads the values a flow passes in ``data``.

        MailTemplate("receipt", subject="Your receipt {{ order_number }}", html="<h1>Thanks, {{ name }}</h1>",
                     variables=[variable("name", sample="Ada"), variable("order_number", sample="A-1042")], category="orders")
    """

    kind: ClassVar[str] = "mail-templates"
    name: str
    subject: str = ""
    html: str = ""
    text: str = ""
    description: str = ""
    preheader: str = ""
    status: Literal["draft", "published", "archived"] = "published"
    category: str = ""
    tags: list[str] = field(default_factory=list)
    folder: str = ""
    variables: list[dict[str, Any]] = field(default_factory=list)

    def problems(self) -> list[str]:
        out = check_name(self.name, "mail template")
        if self.status == "published" and not (self.html or self.text):
            out.append("a published template needs html or text")
        if len(self.preheader) > 255:
            out.append("preheader is at most 255 characters")
        if len(self.category) > 32 or len(self.folder) > 64:
            out.append("category is at most 32 characters and folder at most 64")
        return out
