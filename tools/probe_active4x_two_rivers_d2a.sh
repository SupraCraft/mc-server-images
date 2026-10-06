#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_file="$repo_root/deploy/active4x-two-rivers/d2a/compose.yaml"
output="${1:-$repo_root/probes/active4x/two-rivers-d2a-result.json}"
project="supracraft_two_rivers_d2a_ci"

compose() {
  docker compose -p "$project" -f "$compose_file" "$@"
}

cleanup() {
  compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_minecraft() {
  local deadline=$((SECONDS + 120))
  local cid
  cid="$(compose ps -q minecraft)"
  while (( SECONDS < deadline )); do
    local status
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || true)"
    if [[ "$status" == "healthy" ]]; then
      return 0
    fi
    if [[ "$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || true)" == "exited" ]]; then
      compose logs minecraft
      return 1
    fi
    sleep 2
  done
  compose logs minecraft
  return 1
}

wait_director() {
  local deadline=$((SECONDS + 45))
  while (( SECONDS < deadline )); do
    if compose exec -T director test -f /state/service-ready.json >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  compose logs director
  return 1
}

cleanup
config_file="$(mktemp)"
compose config > "$config_file"

grep -q '127.0.0.1' "$config_file"
if grep -q '25575' "$config_file"; then
  echo "unexpected published/admin port in compose config" >&2
  exit 1
fi

compose build --pull
compose up -d
wait_minecraft
wait_director

logs_initial="$(compose logs minecraft)"
grep -q 'Starting minecraft server version 26.3' <<<"$logs_initial"
grep -q 'SUPRACRAFT_D2A_DATAPACK_LOADED' <<<"$logs_initial"

first_apply="$(compose exec -T director python /app/director_ctl.py apply --operation-id d2a-bootstrap)"
python - "$first_apply" <<'PY'
import json, sys
v=json.loads(sys.argv[1])
assert v["accepted"] is True, v
assert v["revision"] == 1, v
assert v["history_count"] == 1, v
PY

compose exec -T minecraft bash -lc 'printf %s staging-world-ok > /data/world-volume-sentinel.txt'
test "$(compose exec -T minecraft cat /data/world-volume-sentinel.txt | tr -d '\r\n')" = "staging-world-ok"

compose restart minecraft director
wait_minecraft
wait_director
test "$(compose exec -T minecraft cat /data/world-volume-sentinel.txt | tr -d '\r\n')" = "staging-world-ok"

duplicate_apply="$(compose exec -T director python /app/director_ctl.py apply --operation-id d2a-bootstrap)"
python - "$duplicate_apply" <<'PY'
import json, sys
v=json.loads(sys.argv[1])
assert v["accepted"] is False, v
assert v["reason"] == "duplicate_operation", v
assert v["revision"] == 1, v
assert v["history_count"] == 1, v
PY

show_after_restart="$(compose exec -T director python /app/director_ctl.py show)"
python - "$show_after_restart" <<'PY'
import json, sys
v=json.loads(sys.argv[1])
assert v["revision"] == 1, v
assert v["applied"] == ["d2a-bootstrap"], v
assert len(v["history"]) == 1, v
PY

compose down
compose up -d
wait_minecraft
wait_director

sentinel_after_recreate="$(compose exec -T minecraft cat /data/world-volume-sentinel.txt | tr -d '\r\n')"
test "$sentinel_after_recreate" = "staging-world-ok"

show_after_recreate="$(compose exec -T director python /app/director_ctl.py show)"
python - "$show_after_recreate" <<'PY'
import json, sys
v=json.loads(sys.argv[1])
assert v["revision"] == 1, v
assert v["applied"] == ["d2a-bootstrap"], v
assert len(v["history"]) == 1, v
PY

published_port="$(compose port minecraft 25565)"
[[ "$published_port" == 127.0.0.1:* ]]

mkdir -p "$(dirname "$output")"
python - "$output" "$first_apply" "$duplicate_apply" "$show_after_restart" "$show_after_recreate" "$published_port" <<'PY'
import json, sys
from pathlib import Path
out=Path(sys.argv[1])
first=json.loads(sys.argv[2])
dup=json.loads(sys.argv[3])
restart=json.loads(sys.argv[4])
recreate=json.loads(sys.argv[5])
port=sys.argv[6]
result={
  "schema":"supracraft.active4x-two-rivers-d2a-rdte/v0.1",
  "deployment_stage":"D2_persistent_staging_stack_lifecycle",
  "minecraft":{"edition":"java","version":"26.3"},
  "checks":{
    "exact_26_3_server_healthy":True,
    "datapack_loaded":True,
    "loopback_only_game_port":port.startswith("127.0.0.1:"),
    "no_published_admin_port":True,
    "world_volume_survives_restart_and_recreate":True,
    "director_revision_survives_restart_and_recreate":restart["revision"]==1 and recreate["revision"]==1,
    "duplicate_director_operation_rejected":dup.get("reason")=="duplicate_operation",
    "clean_shutdown_restart":True,
    "actor_pool_deferred_to_d2b":True,
    "world_scan_false":True
  },
  "director":{
    "first_apply":first,
    "duplicate_retry":dup,
    "after_restart":restart,
    "after_recreate":recreate
  },
  "published_game_port":port,
  "world_sentinel":"staging-world-ok",
  "world_scan":False,
  "result":"PASS"
}
out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
print(json.dumps(result,indent=2,sort_keys=True))
PY
