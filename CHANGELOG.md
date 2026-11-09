# Changelog

## 0.2.1

Environment settings as code.

* New `EnvironmentSettings` and `Auth` definitions configure an environment's sign-in rules (password policy, lockout, sessions, MFA, directory options, redirect URLs) and general settings (CORS origins, timezone, currency, locale, realtime channels). `Secret` sets an environment secret from your code or an environment variable.
* Plan and deploy compare and apply them like any other definition; flow validation and reference checks were tightened.

## 0.2.0

Agents, knowledge bases and connections as code, vector search on tables, and the server's current flow blocks.

* New definitions: `Agent`, `KnowledgeBase` and `Connection` (`Connection.notion`, `.mcp`, `.web_search`), with `tools.table`, `.flow`, `.web_fetch`, `.web_search`, `.notion`, `.mcp`, `.agent`, `.code`, `.image`, `.x_search` and `.tool_search` for what an agent can use. Checked offline: tools, limits, policies and every reference (tables, flows, connections, knowledge bases, other agents), including an agent handing work to itself.
* `Vector` and `Embed` fields and `hnsw` / `ivfflat` indexes with a `metric`, for searching a table by meaning.
* The flow builder follows the server: 76 blocks in 28 families, now with `blocks.ai` (`chat`, `embed`, `search`, `answer`, `agent`, `knowledge_search`, `knowledge_add`). Flow settings that name an agent, a knowledge base or a table are checked against your definitions.
* **Removed:** `Transformer` and the `transformer=` setting on `Table` and `Route`. The server removed response transformers; the setting was already ignored.
* The block generator handles block names with more than one dot after the family (`ai.knowledge.add` is `blocks.ai.knowledge_add`).

## 0.1.0

First release.

* Define a Pawabase backend as Python: tables (typed fields, constraints, relations, indexes), schemas, transformers, roles, policies (as Python expressions), flows, routes, subscriptions, schedules, webhooks, inbound hooks, buckets and mail templates.
* A flow builder over all 69 server flow blocks, generated from the server's registry, with every option typed and documented.
* Offline validation: each definition, template syntax, block settings, flow graphs, and the references between definitions.
* `pawabase validate | plan | deploy | emulate | init | whoami`; merge and override modes; deploys need a secret API key (a deploy key is enough); table migrations after changes; secrets only through `env()`.
* Conformance tests against the server's own request models and flow validator.
