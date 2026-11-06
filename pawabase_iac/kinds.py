"""Every kind of definition, by the name the Platform API gives it."""

from __future__ import annotations

from .access import Role
from .agents import Agent, Connection, KnowledgeBase
from .api import Route
from .core.base import ORDER, Definition
from .events import InboundHook, Schedule, Subscription, Webhook
from .flows import Flow
from .mail import MailTemplate
from .policies import Policy
from .storage import Bucket
from .tables import Schema, Table

KINDS: dict[str, type[Definition]] = {
    cls.kind: cls
    for cls in (Role, Schema, Policy, Table, Flow, Bucket, MailTemplate, Route, Subscription, Webhook, InboundHook, Schedule, Connection, KnowledgeBase, Agent)
}
assert set(KINDS) == set(ORDER), set(ORDER) ^ set(KINDS)
