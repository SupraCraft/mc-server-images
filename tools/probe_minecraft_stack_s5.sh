#!/usr/bin/env bash
set -euo pipefail
root="$(mktemp -d)"; src="$(mktemp -d)"
printf 'alpha\n' > "$src/level.dat"
python3 tools/minecraft_world_agent.py stage --root "$root" --release r1 --source "$src" | tee /tmp/stage
grep -q '"verb": "stage"' /tmp/stage
python3 tools/minecraft_world_agent.py activate --root "$root" --release r1 | tee /tmp/activate
grep -q '"verb": "activate"' /tmp/activate
h1="$(python3 tools/minecraft_world_agent.py hash --root "$root" | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha256"])')"
printf 'beta\n' > "$src/level.dat"
python3 tools/minecraft_world_agent.py stage --root "$root" --release r2 --source "$src"
python3 tools/minecraft_world_agent.py activate --root "$root" --release r2
python3 tools/minecraft_world_agent.py restore --root "$root" --release r1
h2="$(python3 tools/minecraft_world_agent.py hash --root "$root" | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha256"])')"
test "$h1" = "$h2"
test ! -e /var/run/docker.sock || true
echo "PASS S5 filesystem stage/activate/hash/restore mechanics"
