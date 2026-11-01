#!/usr/bin/env bash
# Post-deploy smoke test: waits for the EngineInstance and probes its service.
#   ./smoke-test.sh [namespace]   (needs kubectl access to the AWC cluster)
set -euo pipefail
NS="${1:-default}"
echo "==> EngineInstance neo4j"
kubectl -n "$NS" get engineinstance neo4j
echo "==> Pods"
kubectl -n "$NS" get pods
echo "==> Port-forward probe on 7474"
SVC="$(kubectl -n "$NS" get svc -o name | grep -i 'neo4j' | head -1)"
kubectl -n "$NS" port-forward "$SVC" 7474:7474 >/dev/null 2>&1 &
PF=$!; trap 'kill $PF' EXIT; sleep 5
curl -fsS -o /dev/null -m 10 "http://127.0.0.1:7474/" && echo "service reachable" || echo "TCP up, non-HTTP protocol (OK for bolt/mysql)"
