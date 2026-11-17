"""Compiling a project into a blueprint zip: a file per concern, env() as variables, parts the kinds don't model, hand-written files."""

import io
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

from pawabase_iac import (
    BlueprintPart,
    EnvironmentSettings,
    Flow,
    MailTemplate,
    Policy,
    Secret,
    String,
    Table,
    collecting,
    crud,
    env,
)
from pawabase_iac.blueprint import compile_bundle

ROOT = Path(__file__).resolve().parent.parent


def run(cwd, *args):
    full = {**os.environ, "PYTHONPATH": str(ROOT), "PAWABASE_API_KEY": ""}
    full.pop("PAWABASE_URL", None)
    return subprocess.run([sys.executable, "-m", "pawabase_iac.cli", *args], cwd=cwd, env=full, capture_output=True, text=True, check=False)


def files_of(data):
    archive = zipfile.ZipFile(io.BytesIO(data))
    return {name: archive.read(name).decode() for name in archive.namelist()}


def compiled(**kwargs):
    with collecting() as registry:
        mine = Policy("mine", True)
        Table("notes", fields=[String("text")], operations=crud(mine))
        Secret("PAYSTACK_KEY", value=env("PAYSTACK_KEY"))
        EnvironmentSettings(auth={"email_code_enabled": True, "providers": {"google": {"client_id": "id", "client_secret": env("GOOGLE_SECRET")}}})
        MailTemplate("welcome", subject="Hi", html="<p>Hello</p>")
        Flow("ping", definition={"nodes": [], "edges": []})
        BlueprintPart("ai", {"providers": {"openai": {"kind": "openai", "key": env("OPENAI_KEY")}}})
        BlueprintPart("data", {"notes": [{"text": "first"}]})
        return compile_bundle(registry.items, registry.parts, name="Notes", environments=["notes"], **kwargs)


def test_a_project_compiles_to_a_bundle_with_a_file_per_concern():
    data, summary = compiled()
    files = files_of(data)
    root = yaml.safe_load(files["blueprint.yml"])
    assert root["blueprint"] == 2 and root["name"] == "Notes" and root["environments"] == ["notes"]
    assert {"tables.yml", "access.yml", "secrets.yml", "auth.yml", "ai.yml", "data.yml", "flows/ping.yml", "mail/welcome.yml"} <= set(files)
    assert root["include"][:3] == ["auth.yml", "secrets.yml", "access.yml"]
    assert "flows/*.yml" in root["include"] and "mail/*.yml" in root["include"]
    assert yaml.safe_load(files["tables.yml"])["tables"][0]["name"] == "notes"
    assert yaml.safe_load(files["data.yml"]) == {"data": {"notes": [{"text": "first"}]}}
    assert summary["counts"]["tables"] == 1 and summary["counts"]["flows"] == 1


def test_env_values_become_declared_variables_and_never_their_values(monkeypatch):
    monkeypatch.setenv("GOOGLE_SECRET", "the-real-secret")
    data, summary = compiled()
    files = files_of(data)
    assert "the-real-secret" not in "".join(files.values())
    assert yaml.safe_load(files["auth.yml"])["auth"]["providers"]["google"]["client_secret"] == "${GOOGLE_SECRET}"
    assert yaml.safe_load(files["secrets.yml"])["secrets"]["PAYSTACK_KEY"]["value"] == "${PAYSTACK_KEY}"
    assert yaml.safe_load(files["ai.yml"])["ai"]["providers"]["openai"]["key"] == "${OPENAI_KEY}"
    assert set(yaml.safe_load(files["blueprint.yml"])["variables"]) == {"GOOGLE_SECRET", "OPENAI_KEY", "PAYSTACK_KEY"}
    assert summary["variables"] == ["GOOGLE_SECRET", "OPENAI_KEY", "PAYSTACK_KEY"]


def test_hand_written_blueprint_files_are_carried_and_included(tmp_path):
    (tmp_path / "status.yml").write_text("status_page: {enabled: true, title: Shop status}\n")
    (tmp_path / "welcome.html").write_text("<h1>Hi</h1>")
    data, _ = compiled(extra_dir=tmp_path)
    files = files_of(data)
    assert files["extra/status.yml"].startswith("status_page") and files["extra/welcome.html"] == "<h1>Hi</h1>"
    assert "extra/*.yml" in yaml.safe_load(files["blueprint.yml"])["include"]


def test_an_unknown_part_is_refused_where_it_is_written():
    with collecting(), pytest.raises(ValueError, match="not a section"):
        BlueprintPart("widgets", {})


def test_the_build_command_writes_the_zip(tmp_path):
    assert run(tmp_path, "init").returncode == 0
    built = run(tmp_path, "build", "-o", "app.zip", "--name", "Todos")
    assert built.returncode == 0, built.stderr
    assert "Wrote app.zip" in built.stdout
    files = files_of((tmp_path / "app.zip").read_bytes())
    assert yaml.safe_load(files["blueprint.yml"])["name"] == "Todos"
    assert "tables.yml" in files
