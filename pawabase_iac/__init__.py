"""Pawabase as code: define a whole backend in Python, validate it, plan it, emulate it, deploy it.

    from pawabase_iac import Table, String, Number, Flow, Route, Policy, P, blocks, ctx, crud

    mine = Policy("mine", P.owner("user_id"))
    orders = Table("orders", fields=[Number("total", required=True)], operations=crud(mine))
"""

from ._version import __version__
from .access import Role
from .agents import Agent, Connection, KnowledgeBase, tools
from .api import Route
from .core import Definition, collecting, env
from .environment import Auth, EnvironmentSettings, Secret
from .events import InboundHook, Schedule, Subscription, Webhook, every
from .expr import ALLOW, DENY, P, Condition, ctx, all_of, any_of, not_
from .flows import Block, Flow, Node, blocks
from .mail import MailTemplate, variable
from .policies import Policy
from .storage import Bucket
from .tables import (
    JSON, ULID, URL, UUID, Allow, Array, BelongsTo, Boolean, Date, DateTime, Deny, Desc, Email, Embed, HasMany, Index, Integer, Number, Object,
    RateLimit, Ref, Resource, Schema, String, Table, Text, Vector, Where, crud, read_only,
)  # fmt: skip

__all__ = [
    "ALLOW", "DENY", "Auth", "EnvironmentSettings", "Secret", "JSON", "P", "ULID", "URL", "UUID", "Agent", "Allow", "Array", "BelongsTo", "Block", "Boolean", "Bucket", "Condition", "Connection",
    "Date", "DateTime", "Definition", "Deny", "Desc", "Email", "Embed", "Flow", "HasMany", "InboundHook", "Index", "Integer", "KnowledgeBase", "MailTemplate", "Node",
    "Number", "Object", "Policy", "RateLimit", "Ref", "Resource", "Role", "Route", "Schedule", "Schema", "String", "Subscription", "Table",
    "Text", "Vector", "Webhook", "Where", "__version__", "all_of", "any_of", "blocks", "collecting", "crud", "ctx", "env", "every",
    "not_", "read_only", "tools", "variable",
]  # fmt: skip
