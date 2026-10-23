import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cwd, *args, env=None):
    full = {**os.environ, "PYTHONPATH": str(ROOT), "PAWABASE_API_KEY": "", **(env or {})}
    full.pop("PAWABASE_URL", None)
    return subprocess.run([sys.executable, "-m", "pawabase_iac.cli", *args], cwd=cwd, env=full, capture_output=True, text=True)


def test_init_validate_emulate(tmp_path):
    assert run(tmp_path, "init").returncode == 0
    assert run(tmp_path, "init").returncode == 1  # already there
    ok = run(tmp_path, "validate")
    assert ok.returncode == 0 and "all valid" in ok.stdout
    first = run(tmp_path, "emulate")
    assert first.returncode == 0 and "8 to create" in first.stdout and "GET /rest/v1/todos" in first.stdout
    second = run(tmp_path, "emulate")
    assert "0 to create" in second.stdout and "8 unchanged" in second.stdout
    assert "8 to create" in run(tmp_path, "emulate", "--reset").stdout


def test_validate_reports_every_problem_and_sends_nothing(tmp_path):
    run(tmp_path, "init")
    (tmp_path / "infra" / "bad.py").write_text(
        "from pawabase_iac import Table, Route, String\nTable('Bad Name', fields=[String('a'), String('a')])\nRoute('/x', handler='ghost')\n"
    )
    out = run(tmp_path, "validate")
    assert out.returncode == 1
    assert "not a valid name" in out.stderr and "duplicate field" in out.stderr and "'ghost' is not defined" in out.stderr


def test_deploy_and_plan_refuse_without_a_key_or_a_secret_key(tmp_path):
    run(tmp_path, "init")
    (tmp_path / "pawabase.toml").write_text('url = "http://127.0.0.1:1"\nenvironment = "development"\nentry = "infra"\n')
    none = run(tmp_path, "deploy")
    assert none.returncode == 1 and "No API key" in none.stderr and "nothing can be pushed" in none.stderr
    publishable = run(tmp_path, "deploy", env={"PAWABASE_API_KEY": "pb_pk_abc"})
    assert publishable.returncode == 1 and "secret key" in publishable.stderr
    unreachable = run(tmp_path, "deploy", env={"PAWABASE_API_KEY": "pb_sk_abc"})
    assert unreachable.returncode == 1 and "Could not reach" in unreachable.stderr


def test_a_project_that_does_not_import_is_reported(tmp_path):
    run(tmp_path, "init")
    (tmp_path / "infra" / "boom.py").write_text("raise RuntimeError('nope')\n")
    out = run(tmp_path, "validate")
    assert out.returncode == 1 and "failed to import" in out.stderr and "nope" in out.stderr
