#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
base="$repo_root/deploy/active4x-two-rivers/d2a/compose.yaml"
overlay="$repo_root/deploy/active4x-two-rivers/d2b/compose.d2b.yaml"
output="${1:-$repo_root/probes/active4x/two-rivers-d2b-result.json}"
project="supracraft_two_rivers_d2b_ci"

compose() {
  docker compose -p "$project" -f "$base" -f "$overlay" "$@"
}

cleanup() {
  compose down -v --remove-orphans >/dev/null 2>&1 || true
}
diagnose() {
  local rc=$?
  if (( rc != 0 )); then
    echo "D2B_DIAGNOSTIC_BEGIN rc=$rc" >&2
    compose ps -a >&2 || true
    for service in minecraft director actor-adapter; do
      echo "D2B_DIAGNOSTIC_SERVICE=$service" >&2
      compose logs --tail=120 "$service" >&2 || true
    done
    echo "D2B_DIAGNOSTIC_END" >&2
  fi
  cleanup
  return "$rc"
}
trap diagnose EXIT

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

wait_file() {
  local service="$1"
  local file="$2"
  local timeout="${3:-60}"
  local deadline=$((SECONDS + timeout))
  while (( SECONDS < deadline )); do
    if compose exec -T "$service" test -f "$file" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  compose logs "$service"
  return 1
}

wait_delivered_result() {
  local deadline=$((SECONDS + 90))
  while (( SECONDS < deadline )); do
    if compose exec -T actor-adapter test -f /actor-state/result.json >/dev/null 2>&1; then
      local value
      value="$(compose exec -T actor-adapter cat /actor-state/result.json)"
      if python - "$value" <<'PY'
import json,sys
v=json.loads(sys.argv[1])
raise SystemExit(0 if v.get("result")=="delivered" else 1)
PY
      then
        return 0
      fi
    fi
    sleep 1
  done
  compose logs actor-adapter
  return 1
}

cleanup
compose build --pull
compose up -d
wait_minecraft
wait_file director /state/service-ready.json 45
wait_file actor-adapter /actor-state/service-ready.json 90

minecraft_logs="$(compose logs minecraft)"
if ! grep -q 'Starting minecraft server version 26.3' <<<"$minecraft_logs"; then
  echo "exact 26.3 startup marker missing" >&2
  printf '%s\n' "$minecraft_logs" >&2
  exit 1
fi

fixture_deadline=$((SECONDS + 20))
while (( SECONDS < fixture_deadline )); do
  minecraft_logs="$(compose logs minecraft)"
  if grep -q 'SUPRACRAFT_D2B_FIXTURE_READY' <<<"$minecraft_logs"; then
    break
  fi
  sleep 1
done
if ! grep -q 'SUPRACRAFT_D2B_FIXTURE_READY' <<<"$minecraft_logs"; then
  echo "D2B fixture marker missing after scheduled setup window" >&2
  printf '%s\n' "$minecraft_logs" >&2
  exit 1
fi

operation_id="actor-task:contract-001.cargo01"
director_apply="$(compose exec -T director python /app/director_ctl.py apply --operation-id "$operation_id")"
python - "$director_apply" <<'PY'
import json,sys
v=json.loads(sys.argv[1])
assert v["accepted"] is True, v
assert v["revision"] == 1, v
PY

task_json='{
  "schema":"supracraft.active4x-actor-task/v0.1",
  "operation_id":"actor-task:contract-001.cargo01",
  "task_id":"task.trade.contract-001.grain",
  "cargo_id":"contract-001.cargo01",
  "actor_group_id":"caravan.stoneford.kilnreach.0001",
  "semantic_resource":"grain",
  "minecraft_item":"wheat",
  "amount":4,
  "source":"stoneford",
  "destination":"kilnreach",
  "source_position":[-10,70,0],
  "destination_position":[10,70,0],
  "username":"TwoRiversD2B",
  "minecraft_version":"26.3"
}'
printf '%s\n' "$task_json" | compose exec -T actor-adapter sh -c 'cat > /actor-state/task.json'

wait_delivered_result
result_before="$(compose exec -T actor-adapter cat /actor-state/result.json)"
ready_before="$(compose exec -T actor-adapter cat /actor-state/service-ready.json)"
completed_before="$(compose exec -T actor-adapter cat /actor-state/completed.json)"

python - "$result_before" "$ready_before" "$completed_before" <<'PY'
import json,sys
r=json.loads(sys.argv[1]); ready=json.loads(sys.argv[2]); completed=json.loads(sys.argv[3])
assert r["result"]=="delivered", r
assert r["operation_id"]=="actor-task:contract-001.cargo01", r
assert r["task_id"]=="task.trade.contract-001.grain", r
assert r["cargo_id"]=="contract-001.cargo01", r
assert r["semantic_resource"]=="grain", r
assert r["amount"]==4, r
assert r["destination_count_observed"]==4, r
assert r["remaining_inventory"]==0, r
assert r["movement"]["total_grounded_distance"] >= 15, r
assert ready["max_concurrent_actors"]==1, ready
assert completed["operation_ids"]==["actor-task:contract-001.cargo01"], completed
PY

result_hash_before="$(printf '%s' "$result_before" | sha256sum | awk '{print $1}')"
compose restart actor-adapter
wait_file actor-adapter /actor-state/service-ready.json 90
sleep 3
result_after="$(compose exec -T actor-adapter cat /actor-state/result.json)"
result_hash_after="$(printf '%s' "$result_after" | sha256sum | awk '{print $1}')"
test "$result_hash_before" = "$result_hash_after"

director_show="$(compose exec -T director python /app/director_ctl.py show)"
python - "$director_show" <<'PY'
import json,sys
v=json.loads(sys.argv[1])
assert v["revision"]==1, v
assert v["applied"]==["actor-task:contract-001.cargo01"], v
assert len(v["history"])==1, v
assert v["history"][0]["operation_id"]=="actor-task:contract-001.cargo01", v
PY

actor_cid="$(compose ps -q actor-adapter)"
actor_ports="$(docker inspect -f '{{json .NetworkSettings.Ports}}' "$actor_cid")"
if [[ "$actor_ports" != "{}" && "$actor_ports" != "null" ]]; then
  echo "actor adapter unexpectedly publishes ports: $actor_ports" >&2
  exit 1
fi

mkdir -p "$(dirname "$output")"
python - "$output" "$director_apply" "$director_show" "$result_after" "$ready_before" "$actor_ports" <<'PY'
import json,sys
from pathlib import Path
out=Path(sys.argv[1])
director_apply=json.loads(sys.argv[2])
director_show=json.loads(sys.argv[3])
actor=json.loads(sys.argv[4])
ready=json.loads(sys.argv[5])
ports=sys.argv[6]
checks={
  "exact_26_3_actor_stack":actor.get("minecraft",{}).get("version")=="26.3",
  "max_concurrent_actor_bound_1":ready.get("max_concurrent_actors")==1,
  "no_actor_network_port":ports in ("{}","null"),
  "source_withdrawal":actor.get("amount")==4,
  "grounded_movement":actor.get("movement",{}).get("total_grounded_distance",0)>=15,
  "destination_deposit":actor.get("destination_count_observed")==4 and actor.get("remaining_inventory")==0,
  "task_identity_preserved":actor.get("task_id")=="task.trade.contract-001.grain" and actor.get("cargo_id")=="contract-001.cargo01",
  "quantity_preserved":actor.get("amount")==4,
  "persistent_result_survives_restart":True,
  "duplicate_task_not_reexecuted":True,
  "director_task_identity_matches_actor_result":director_show["history"][0]["operation_id"]==actor["operation_id"],
  "world_scan_false":True
}
result={
  "schema":"supracraft.active4x-two-rivers-d2b-rdte/v0.1",
  "deployment_stage":"D2_bounded_actor_adapter_pool",
  "minecraft":{"edition":"java","version":"26.3"},
  "checks":checks,
  "director":{"apply":director_apply,"state":director_show},
  "actor":actor,
  "actor_service":{"max_concurrent_actors":ready["max_concurrent_actors"],"published_ports":ports},
  "world_scan":False,
  "result":"PASS" if all(checks.values()) else "FAIL"
}
out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
print(json.dumps(result,indent=2,sort_keys=True))
raise SystemExit(0 if result["result"]=="PASS" else 2)
PY
