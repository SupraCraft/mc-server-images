#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
base="$repo_root/deploy/active4x-two-rivers/d2a/compose.yaml"
actor="$repo_root/deploy/active4x-two-rivers/d2b/compose.d2b.yaml"
hil="$repo_root/deploy/active4x-two-rivers/d3/compose.d3.yaml"
rehearsal="$repo_root/deploy/active4x-two-rivers/d3/compose.rehearsal.yaml"
output="${1:-$repo_root/probes/active4x/two-rivers-d3-rehearsal-result.json}"
project="supracraft_two_rivers_d3_rehearsal"

compose() {
  docker compose -p "$project" -f "$base" -f "$actor" -f "$hil" -f "$rehearsal" "$@"
}

cleanup() {
  compose down -v --remove-orphans >/dev/null 2>&1 || true
}
stage="startup"
diagnose() {
  local rc=$?
  trap - EXIT
  if (( rc != 0 )); then
    echo "D3_REHEARSAL_DIAGNOSTIC_BEGIN rc=$rc stage=$stage" >&2
    local evidence_dir scratch hil_cid
    evidence_dir="$(dirname "$output")"
    mkdir -p "$evidence_dir"
    scratch="$(mktemp -d)"
    hil_cid="$(compose ps -aq hil-probe 2>/dev/null | head -n 1 || true)"

    # Capture the original client's success/error receipt BEFORE deleting volumes.
    if [[ -n "$hil_cid" ]]; then
      docker cp "$hil_cid:/hil-state/result-interact.json" "$scratch/original.json" >/dev/null 2>&1 || true
    fi

    # One bounded, observational fresh client: its chunk data can falsify the
    # original client's predicted dig success. No blocks are modified.
    if [[ -n "$hil_cid" ]] && compose ps -q minecraft >/dev/null 2>&1; then
      compose run --rm --no-deps -T -e HIL_MODE=diagnose hil-probe >"$scratch/fresh-client.log" 2>&1 || true
      docker cp "$hil_cid:/hil-state/result-diagnose.json" "$scratch/fresh.json" >/dev/null 2>&1 || true
    fi

    compose logs --no-color --tail=250 minecraft >"$scratch/server.log" 2>/dev/null || true
    # Produce a compact, fail-closed, public-safe receipt even when the client
    # or the diagnostic itself failed. Do not promote client prediction to a
    # stock-server event or convert a red run to green.
    python3 - "$output" "$scratch" "$stage" "$rc" <<'PY'
import json, sys
from pathlib import Path

out, directory, stage, rc = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], int(sys.argv[4])

def get_json(name):
    try:
        return json.loads((directory / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

original, fresh = get_json("original.json"), get_json("fresh.json")
try:
    log = (directory / "server.log").read_text(encoding="utf-8")
except OSError:
    log = ""
names = (
    "SUPRACRAFT_D3_TRADE_COMPLETE",
    "SUPRACRAFT_D3_BUILD_HELP_COMPLETE",
    "SUPRACRAFT_D3_OBSTRUCT_COMPLETE",
    "SUPRACRAFT_D3_DAMAGE_COMPLETE",
    "SUPRACRAFT_D3_PHASE1_COMPLETE",
)
markers = {name: name in log for name in names}
# Fixed fixture fields only: no credentials, environment, or arbitrary logs.
client = None if original is None else {
    "mode": original.get("mode"),
    "result": original.get("result"),
    "actions": original.get("actions"),
    "minecraft": original.get("minecraft"),
    "error": str(original.get("error", ""))[:1500] or None,
}
fresh_blocks = (fresh.get("blocks") if isinstance(fresh, dict) else None)
receipt = {
    "schema": "supracraft.active4x-two-rivers-d3-rehearsal/v0.1",
    "deployment_stage": "D3_automated_rehearsal",
    "result": "FAIL",
    "failed_stage": stage,
    "harness_exit_code": rc,
    "client_interaction": client,
    "fresh_client_block_observation": fresh_blocks,
    "fresh_client_observation_status": fresh.get("result") if isinstance(fresh, dict) else "UNKNOWN",
    "server_markers": markers,
    "server_authoritative_block_state": "UNKNOWN",
    "stock_client_hil_required": True,
    "world_scan": False,
    "diagnostic_only": True,
}
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(receipt, sort_keys=True))
PY
    rm -rf "$scratch"
    compose ps -a >&2 || true
    for service in minecraft director actor-adapter hil-probe; do
      echo "D3_REHEARSAL_DIAGNOSTIC_SERVICE=$service" >&2
      compose logs --tail=60 "$service" >&2 || true
    done
    echo "D3_REHEARSAL_DIAGNOSTIC_END" >&2
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
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || true)"
    [[ "$status" == "healthy" ]] && return 0
    if [[ "$status" == "unhealthy" || "$status" == "exited" ]]; then
      compose logs minecraft >&2
      return 1
    fi
    sleep 2
  done
  compose logs minecraft >&2
  return 1
}

wait_exec_file() {
  local service="$1" file="$2" timeout="${3:-90}"
  local deadline=$((SECONDS + timeout))
  while (( SECONDS < deadline )); do
    if compose exec -T "$service" test -f "$file" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

wait_marker() {
  local marker="$1" timeout="${2:-90}"
  local deadline=$((SECONDS + timeout))
  while (( SECONDS < deadline )); do
    if compose logs minecraft 2>/dev/null | grep -q "$marker"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

wait_actor_delivered() {
  local deadline=$((SECONDS + 120))
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
  return 1
}

wait_hil_probe_exit() {
  local cid="$1" timeout="${2:-120}"
  local deadline=$((SECONDS + timeout))
  while (( SECONDS < deadline )); do
    local state
    state="$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || true)"
    if [[ "$state" == "exited" ]]; then
      local code
      code="$(docker inspect -f '{{.State.ExitCode}}' "$cid")"
      [[ "$code" == "0" ]]
      return
    fi
    sleep 1
  done
  return 1
}

cleanup
compose build --pull
compose up -d minecraft director actor-adapter hil-probe
wait_minecraft
wait_exec_file director /state/service-ready.json 60
wait_exec_file actor-adapter /actor-state/service-ready.json 90
wait_exec_file hil-probe /hil-state/ready.json 90
wait_marker SUPRACRAFT_D2B_FIXTURE_READY 45
wait_marker SUPRACRAFT_D3_HIL_READY 45

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
printf '%s\n' "$task_json" | compose exec -T actor-adapter sh -c 'cat > /actor-state/task.json.tmp && mv /actor-state/task.json.tmp /actor-state/task.json'
compose exec -T hil-probe sh -c 'touch /hil-state/go'

hil_cid="$(compose ps -q hil-probe)"
stage="hil_probe_exit"
wait_hil_probe_exit "$hil_cid" 150
stage="actor_delivery"
wait_actor_delivered
for marker in SUPRACRAFT_D3_TRADE_COMPLETE SUPRACRAFT_D3_BUILD_HELP_COMPLETE SUPRACRAFT_D3_OBSTRUCT_COMPLETE SUPRACRAFT_D3_DAMAGE_COMPLETE SUPRACRAFT_D3_PHASE1_COMPLETE; do
  stage="await_$marker"
  wait_marker "$marker" 60
done

tmp_interact="$(mktemp)"
docker cp "$hil_cid:/hil-state/result-interact.json" "$tmp_interact"
hil_interact="$(cat "$tmp_interact")"
rm -f "$tmp_interact"
python - "$hil_interact" <<'PY'
import json,sys
v=json.loads(sys.argv[1])
assert v["result"]=="PASS", v
assert v["minecraft"]["version"]=="26.3", v
assert v["caravan"]["seen"] is True, v
assert v["trade_output_bricks"] >= 2, v
assert all(v["actions"].values()), v
PY

actor_result="$(compose exec -T actor-adapter cat /actor-state/result.json)"
python - "$actor_result" <<'PY'
import json,sys
v=json.loads(sys.argv[1])
assert v["result"]=="delivered", v
assert v["task_id"]=="task.trade.contract-001.grain", v
assert v["cargo_id"]=="contract-001.cargo01", v
assert v["amount"]==4, v
PY

compose restart minecraft
wait_minecraft
wait_marker SUPRACRAFT_D3_STATE_SURVIVED_RESTART 60

compose run --rm --no-deps -T -e HIL_MODE=rejoin hil-probe
hil_rejoin="$(compose run --rm --no-deps -T hil-probe sh -c 'cat /hil-state/result-rejoin.json')"
python - "$hil_rejoin" <<'PY'
import json,sys
v=json.loads(sys.argv[1])
assert v["result"]=="PASS", v
assert v["mode"]=="rejoin", v
assert v["minecraft"]["version"]=="26.3", v
assert v["joined"] is True, v
PY

director_show="$(compose exec -T director python /app/director_ctl.py show)"
python - "$director_show" <<'PY'
import json,sys
v=json.loads(sys.argv[1])
assert v["revision"]==1, v
assert v["applied"]==["actor-task:contract-001.cargo01"], v
assert len(v["history"])==1, v
PY

mkdir -p "$(dirname "$output")"
python - "$output" "$director_apply" "$director_show" "$actor_result" "$hil_interact" "$hil_rejoin" <<'PY'
import json,sys
from pathlib import Path
out=Path(sys.argv[1])
director_apply=json.loads(sys.argv[2])
director_state=json.loads(sys.argv[3])
actor=json.loads(sys.argv[4])
interaction=json.loads(sys.argv[5])
rejoin=json.loads(sys.argv[6])
checks={
  "exact_26_3_rehearsal_client":interaction.get("minecraft",{}).get("version")=="26.3",
  "trade_path":interaction.get("actions",{}).get("trade_deposit") is True and interaction.get("trade_output_bricks",0)>=2,
  "construction_help_path":interaction.get("actions",{}).get("build_supply") is True,
  "construction_obstruction_path":interaction.get("actions",{}).get("obstruction_break") is True,
  "damage_path":interaction.get("actions",{}).get("damage_break") is True,
  "caravan_encounter_path":interaction.get("caravan",{}).get("seen") is True and actor.get("result")=="delivered",
  "restart_recovery_path":rejoin.get("joined") is True,
  "semantic_revision_monotonic":director_state.get("revision")==1,
  "stock_client_hil_not_claimed":True,
  "world_scan_false":True
}
result={
  "schema":"supracraft.active4x-two-rivers-d3-rehearsal/v0.1",
  "deployment_stage":"D3_automated_rehearsal",
  "checks":checks,
  "interaction_client":interaction,
  "caravan_actor":actor,
  "rejoin_client":rejoin,
  "director":{"apply":director_apply,"state":director_state},
  "stock_client_hil_required":True,
  "world_scan":False,
  "result":"PASS" if all(checks.values()) else "FAIL"
}
out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
print(json.dumps(result,indent=2,sort_keys=True))
raise SystemExit(0 if result["result"]=="PASS" else 2)
PY
