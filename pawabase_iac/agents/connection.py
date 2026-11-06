from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from ..core.base import Definition, check_name

SEARCH_PROVIDERS = ("tavily", "exa", "duckduckgo")
KEYLESS_SEARCH = ("duckduckgo",)
MCP_AUTH = ("bearer", "header", "basic")


@dataclass
class Connection(Definition):
    """An outside service an agent can reach: web search, Notion, or any app with an MCP server.

        Connection.notion("wiki", secret="NOTION_KEY")
        Connection.mcp("github", "https://api.githubcopilot.com/mcp/", secret="GITHUB_TOKEN")
        Connection.mcp("jira", "https://mcp.atlassian.com/v1/mcp", secret="JIRA_TOKEN", auth="basic", username="you@example.com")
        Connection.web_search("exa", provider="exa", secret="EXA_KEY")

    ``secret`` is the *name* of an environment secret that holds the key (set it with the secrets API or Studio), never the key itself.
    """

    kind: ClassVar[str] = "connections"
    name: str
    #: What it connects to: ``web_search``, ``notion`` or ``mcp``.
    service: Literal["web_search", "notion", "mcp"] = "mcp"
    config: dict[str, Any] = field(default_factory=dict)
    secret: str = ""
    description: str = ""
    enabled: bool = True

    @classmethod
    def notion(cls, name: str, *, secret: str, **options: Any) -> Connection:
        return cls(name, service="notion", secret=secret, **options)

    @classmethod
    def web_search(cls, name: str, *, provider: Literal["tavily", "exa", "duckduckgo"], secret: str = "", **options: Any) -> Connection:
        return cls(name, service="web_search", config={"provider": provider}, secret=secret, **options)

    @classmethod
    def mcp(cls, name: str, url: str, *, secret: str = "", auth: Literal["bearer", "header", "basic"] | None = None, header: str | None = None,
            scheme: str | None = None, username: str | None = None, **options: Any) -> Connection:
        """An MCP server. Most take a bearer token. ``header="X-Api-Key"`` sends the key in a header of your choosing, ``scheme="Sentry-Bearer"``
        changes the word before it, and ``auth="basic"`` with ``username`` sends an email and a token (Atlassian)."""
        config = {"url": url, "auth": auth, "header": header, "scheme": scheme, "username": username}
        return cls(name, service="mcp", config={k: v for k, v in config.items() if v is not None}, secret=secret, **options)

    def body(self, *, resolve: bool = True) -> dict[str, Any]:
        body = super().body(resolve=resolve)
        body["kind"] = body.pop("service")  # the server calls what it connects to its kind
        return body

    def problems(self) -> list[str]:
        out = check_name(self.name, "connection")
        if self.service not in ("web_search", "notion", "mcp"):
            return out + [f"service is web_search, notion or mcp, not {self.service!r}"]
        if self.service == "web_search":
            provider = self.config.get("provider")
            if provider not in SEARCH_PROVIDERS:
                out.append(f"choose a search provider: {', '.join(SEARCH_PROVIDERS)}")
            elif provider not in KEYLESS_SEARCH and not self.secret:
                out.append(f"{provider} search needs the name of the secret that holds its key")
        if self.service == "notion" and not self.secret:
            out.append("Notion needs the name of the secret that holds its integration secret")
        if self.service == "mcp":
            if not str(self.config.get("url", "")).startswith(("http://", "https://")):
                out.append("an MCP connection needs the server's http or https address")
            auth = self.config.get("auth")
            if auth is not None and auth not in MCP_AUTH:
                out.append(f"auth is one of {', '.join(MCP_AUTH)}")
            if auth == "basic" and not str(self.config.get("username") or "").strip():
                out.append("signing in with a key and an email needs the email, as username")
            if auth == "header" and not str(self.config.get("header") or "").strip():
                out.append("name the header the key goes in")
        return out
