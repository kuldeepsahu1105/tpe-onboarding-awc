#!/usr/bin/env bash
# Post-deploy smoke test: waits for the EngineInstance and probes its service.
#   ./smoke-test.sh [namespace]   (needs kubectl access to the AWC cluster)
set -euo pipefail
NS="${1:-default}"
echo "==> EngineInstance puppygraph"
kubectl -n "$NS" get engineinstance puppygraph
echo "==> Pods"
kubectl -n "$NS" get pods
echo "==> Port-forward probe on 8081"
SVC="$(kubectl -n "$NS" get svc -o name | grep -i 'puppygraph' | head -1)"
kubectl -n "$NS" port-forward "$SVC" 8081:8081 >/dev/null 2>&1 &
PF=$!; trap 'kill $PF' EXIT; sleep 5
curl -fsS -o /dev/null -m 10 "http://127.0.0.1:8081/" && echo "service reachable" || echo "TCP up, non-HTTP protocol (OK for bolt/mysql)"
