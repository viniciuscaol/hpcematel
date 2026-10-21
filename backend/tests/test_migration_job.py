"""Exercita o script real de migração com kubectl simulado, sem cluster."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrate.sh"


@pytest.fixture
def runner(tmp_path):
    kubectl = tmp_path / "kubectl"
    kubectl.write_text(f"#!{sys.executable}\n" + '''
import json, os, pathlib, sys
args = sys.argv[1:]
root = pathlib.Path(os.environ["FAKE_KUBE_ROOT"])
with (root / "calls.jsonl").open("a") as f:
    f.write(json.dumps(args) + "\\n")
if "create" in args:
    (root / "job.yaml").write_text(sys.stdin.read())
    sys.exit(int(os.environ.get("CREATE_EXIT", "0")))
if any(a.startswith("jsonpath=") for a in args):
    state = root / "polls"
    count = int(state.read_text()) if state.exists() else 0
    state.write_text(str(count + 1))
    states = json.loads(os.environ.get("JOB_STATES", '["True,"]'))
    print(states[min(count, len(states) - 1)])
    sys.exit(int(os.environ.get("GET_EXIT", "0")))
if "logs" in args:
    print("logs simulados da migração")
    sys.exit(int(os.environ.get("LOGS_EXIT", "0")))
''')
    kubectl.chmod(0o755)
    sleep = tmp_path / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n")
    sleep.chmod(0o755)

    def run(**variables):
        env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "FAKE_KUBE_ROOT": str(tmp_path), **variables}
        result = subprocess.run(
            ["bash", str(SCRIPT), "chamados-cematel-homolog", "ghcr.io/test/helpdesk:commit", "migrate-test-1"],
            env=env, text=True, capture_output=True, timeout=10,
        )
        calls_file = tmp_path / "calls.jsonl"
        calls = [json.loads(line) for line in calls_file.read_text().splitlines()] if calls_file.exists() else []
        manifest_file = tmp_path / "job.yaml"
        manifest = yaml.safe_load(manifest_file.read_text()) if manifest_file.exists() else None
        return result, calls, manifest

    return run


def test_aguarda_job_completo_e_preserva_pod(runner):
    result, calls, manifest = runner(JOB_STATES='[",", "True,"]')
    assert result.returncode == 0, result.stderr
    assert len([c for c in calls if any(a.startswith("jsonpath=") for a in c)]) == 2
    assert any("logs" in c for c in calls)
    assert not any("delete" in c for c in calls)
    assert all(c[:3] == ["--namespace", "chamados-cematel-homolog", "--request-timeout=20s"] for c in calls)
    assert manifest["kind"] == "Job"
    assert manifest["spec"]["activeDeadlineSeconds"] == 600
    assert manifest["spec"]["backoffLimit"] == 0
    assert manifest["spec"]["ttlSecondsAfterFinished"] == 86400
    container = manifest["spec"]["template"]["spec"]["containers"][0]
    assert container["command"] == ["alembic", "upgrade", "head"]
    assert container["image"] == "ghcr.io/test/helpdesk:commit"
    assert container["envFrom"] == [{"configMapRef": {"name": "helpdesk-config"}}, {"secretRef": {"name": "helpdesk-secrets"}}]


@pytest.mark.parametrize("logs_exit", ["0", "1"])
def test_falha_do_job_bloqueia_deploy_e_coleta_diagnostico(runner, logs_exit):
    result, calls, _ = runner(JOB_STATES='[",True"]', LOGS_EXIT=logs_exit)
    assert result.returncode == 1
    assert any("describe" in c and "job" in c for c in calls)
    assert any("describe" in c and "pods" in c for c in calls)
    assert any("logs" in c for c in calls)
    assert not any("delete" in c for c in calls)


def test_falha_na_coleta_de_logs_nao_invalida_migracao_concluida(runner):
    result, _, _ = runner(LOGS_EXIT="1")
    assert result.returncode == 0


@pytest.mark.parametrize("variables,expected", [({"CREATE_EXIT": "17"}, 17), ({"GET_EXIT": "5"}, 5)])
def test_erro_do_kubectl_nao_e_tratado_como_sucesso(runner, variables, expected):
    result, calls, _ = runner(**variables)
    assert result.returncode == expected
    assert any("describe" in c for c in calls)


def test_limite_invalido_nao_cria_job(runner):
    result, calls, _ = runner(MIGRATION_TIMEOUT_SECONDS="0")
    assert result.returncode == 2
    assert calls == []
