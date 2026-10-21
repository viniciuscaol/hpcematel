#!/usr/bin/env bash
# Executa uma migração por Job, sem depender de attach/stdin do kubectl run.
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "Uso: bash scripts/migrate.sh NAMESPACE IMAGEM NOME_DO_JOB" >&2
  exit 2
fi

namespace=$1
image=$2
job=$3
timeout_seconds=${MIGRATION_TIMEOUT_SECONDS:-600}
if [[ ! $timeout_seconds =~ ^[1-9][0-9]*$ ]]; then
  echo "MIGRATION_TIMEOUT_SECONDS deve ser um inteiro positivo." >&2
  exit 2
fi

kube() {
  kubectl --namespace "$namespace" --request-timeout=20s "$@"
}

diagnosticar() {
  local resultado=$?
  trap - EXIT
  if [[ $resultado -ne 0 ]]; then
    echo "Migração falhou. Coletando estado e eventos do Job $job..." >&2
    kube get job "$job" -o wide || true
    kube describe job "$job" || true
    kube get pods -l "job-name=$job" -o wide || true
    kube describe pods -l "job-name=$job" || true
  fi
  kube logs "job/$job" --all-containers=true --timestamps=true --tail=200 || true
  exit "$resultado"
}
trap diagnosticar EXIT

# Sem retries automáticos para não repetir migrações que falharam parcialmente.
# O Job e o pod ficam disponíveis para investigação por até 24h após terminar.
kube create -f - <<YAML
apiVersion: batch/v1
kind: Job
metadata:
  name: "$job"
spec:
  backoffLimit: 0
  activeDeadlineSeconds: $timeout_seconds
  ttlSecondsAfterFinished: 86400
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: migrate
          image: "$image"
          imagePullPolicy: Always
          command: ["alembic", "upgrade", "head"]
          envFrom:
            - configMapRef:
                name: helpdesk-config
            - secretRef:
                name: helpdesk-secrets
YAML

echo "Aguardando migração no namespace $namespace (limite: ${timeout_seconds}s)..."
deadline=$((SECONDS + timeout_seconds + 30))
while (( SECONDS < deadline )); do
  estado=$(kube get job "$job" -o 'jsonpath={.status.conditions[?(@.type=="Complete")].status},{.status.conditions[?(@.type=="Failed")].status}')
  if [[ $estado == True,* ]]; then
    echo "Migração concluída com sucesso."
    exit 0
  fi
  if [[ $estado == *,True ]]; then
    echo "O Job de migração informou falha." >&2
    exit 1
  fi
  sleep 5
done

echo "Timeout aguardando a conclusão da migração." >&2
exit 1
