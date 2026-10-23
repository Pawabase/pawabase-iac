# Changelog

## 0.1.0

First release.

* Define a Pawabase backend as Python: tables (typed fields, constraints, relations, indexes), schemas, transformers, roles, policies (as Python expressions), flows, routes, subscriptions, schedules, webhooks, inbound hooks, buckets and mail templates.
* A flow builder over all 69 server flow blocks, generated from the server's registry, with every option typed and documented.
* Offline validation: each definition, template syntax, block settings, flow graphs, and the references between definitions.
* `pawabase validate | plan | deploy | emulate | init | whoami`; merge and override modes; deploys need a secret API key (a deploy key is enough); table migrations after changes; secrets only through `env()`.
* Conformance tests against the server's own request models and flow validator.
