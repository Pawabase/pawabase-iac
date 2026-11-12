"""Environment settings (auth, settings) and secrets as definitions."""

from pawabase_iac import Auth, EnvironmentSettings, Secret, env
from pawabase_iac.core import collecting
from pawabase_iac.engine.plan import apply_plan, build_plan
from pawabase_iac.environments import EmulatedEnvironment
from pawabase_iac.validate import check


def test_a_good_environment_is_valid():
    with collecting() as registry:
        EnvironmentSettings(auth=Auth(signup_enabled=True, password_min_length=12, directory={"api_keys": {"enabled": True, "max_per_user": 5}, "mfa": {"require": "admins"}}), settings={"cors_origins": ["https://a.example.com"], "shop_suffix": "x.example.com"})
    assert check(registry.items) == []


def test_mistakes_are_named():
    with collecting() as registry:
        EnvironmentSettings(auth=Auth(signup_enabld=True, password_min_length=2, directory={"api_keys": {"max_per_user": 500}, "mfa": {"require": "sometimes"}, "nope": {}}), settings={"bad-key": 1})
    text = " ".join(p.message for p in check(registry.items))
    for fragment in ("signup_enabld", "password_min_length", "api_keys.max_per_user", "mfa.require", "directory.nope", "bad-key"):
        assert fragment in text


def test_deploy_sets_it_once_and_a_secret_is_not_compared(monkeypatch):
    monkeypatch.setenv("TOKEN_VALUE", "s3cret-value-123456")
    with collecting() as registry:
        EnvironmentSettings(auth=Auth(signup_enabled=False))
        Secret("TOKEN", value=env("TOKEN_VALUE"))
    emulated = EmulatedEnvironment()
    plan = build_plan(registry.items, emulated)
    assert {c.label for c in plan.pending} == {"environment/settings", "secrets/TOKEN"}
    apply_plan(plan, registry.items, emulated)
    again = build_plan(registry.items, emulated)
    assert not again.pending


def test_flow_tags_are_sent_only_when_set():
    from pawabase_iac import Flow

    plain = Flow("plain_tags_check")
    tagged = Flow("tagged_tags_check", tags=["billing", "orders"])
    assert "tags" not in plain.body()
    assert tagged.body()["tags"] == ["billing", "orders"]


def test_mail_template_design_is_sent_only_when_set():
    from pawabase_iac import MailTemplate

    doc = {"type": "doc", "content": [{"type": "paragraph"}]}
    designed = MailTemplate("receipt", subject="Hi", html="<p>Hi</p>", design={"doc": doc, "theme": {}})
    assert designed.problems() == []
    assert designed.body()["design"] == {"doc": doc, "theme": {}}
    assert "design" not in MailTemplate("plain", subject="Hi", html="<p>Hi</p>").body()
    assert MailTemplate("bad", subject="Hi", html="<p>Hi</p>", design={"theme": {}}).problems()
