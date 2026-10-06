#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
base="$repo_root/deploy/active4x-two-rivers/d2a/compose.yaml"
overlay="$repo_root/deploy/active4x-two-rivers/d3/compose.d3.yaml"
output="${1:-$repo_root/probes/active4x/two-rivers-d3-preflight-result.json}"
project="supracraft_two_rivers_d3_preflight"

compose() {
  docker compose -p "$project" -f "$base" -f "$overlay" "$@"
}

cleanup() {
  compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_minecraft() {
  local deadline=$((SECONDS + 150))
  local cid
  cid="$(compose ps -q minecraft)"
  while (( SECONDS < deadline )); do
    local status
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || true)"
    if [[ "$status" == "healthy" ]]; then return 0; fi
    if [[ "$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || true)" == "exited" ]]; then
      compose logs minecraft
      return 1
    fi
    sleep 2
  done
  compose logs minecraft
  return 1
}

cleanup
compose build --pull minecraft
compose up -d minecraft
wait_minecraft

deadline=$((SECONDS + 30))
hil_ready=false
while (( SECONDS < deadline )); do
  logs="$(compose logs minecraft)"
  if grep -q 'SUPRACRAFT_D3_HIL_READY' <<<"$logs"; then
    hil_ready=true
    break
  fi
  sleep 1
done

logs="$(compose logs minecraft)"
grep -q 'Starting minecraft server version 26.3' <<<"$logs"
grep -q 'SUPRACRAFT_D2A_DATAPACK_LOADED' <<<"$logs"
test "$hil_ready" = "true"

if grep -Ei 'Failed to load|pack.*error|ERROR' <<<"$logs" >/dev/null; then
  echo "D3 preflight found server/datapack errors" >&2
  printf '%s\n' "$logs" >&2
  exit 1
fi

mkdir -p "$(dirname "$output")"
python - "$output" <<'PY'
import json,sys
from pathlib import Path
out=Path(sys.argv[1])
checks={
  "exact_26_3_server_healthy":True,
  "d2a_datapack_loaded":True,
  "d3_hil_datapack_loaded":True,
  "hil_fixture_ready":True,
  "human_acceptance_not_claimed":True,
  "world_scan_false":True
}
result={
  "schema":"supracraft.active4x-two-rivers-d3-preflight/v0.1",
  "deployment_stage":"D3_stock_client_hil_preflight",
  "checks":checks,
  "stock_client_hil_required":True,
  "world_scan":False,
  "result":"PASS" if all(checks.values()) else "FAIL"
}
out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
print(json.dumps(result,indent=2,sort_keys=True))
PY
