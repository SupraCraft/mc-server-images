#!/usr/bin/env bash
set -euo pipefail
d="$(mktemp -d)"
trap 'rm -rf "$d"' EXIT
url='https://piston-data.mojang.com/v1/objects/33680f5f2ac32864d6d7cf5e56a705fdb3e05f4c/server.jar'
curl -fsSL --retry 2 "$url" -o "$d/server.jar"
echo 'd052f14d7a173734fba553711e5b570162e2f2a313267ee31a21b975a679be64  '"$d/server.jar" | sha256sum -c -
inner="$(unzip -Z1 "$d/server.jar" | grep -E '(^|/)server-26[.]3[.]jar$' | head -n1 || true)"
if [[ -n "$inner" ]]; then
  unzip -p "$d/server.jar" "$inner" > "$d/inner.jar"
else
  cp "$d/server.jar" "$d/inner.jar"
fi
javap -p -classpath "$d/inner.jar" net.minecraft.server.level.ServerPlayerGameMode > "$d/methods.txt"
python3 - "$d/methods.txt" <<'PY'
import json, re, sys
from pathlib import Path
t=Path(sys.argv[1]).read_text()
methods=['tick','handleBlockBreakAction','incrementDestroyProgress','destroyAndAck','destroyBlock','abortDestroyBlock']
found={m:bool(re.search(r'\b'+m+r'\s*\(',t)) for m in methods}
report={'schema':'supracraft.d3-handler-shape/v0.1','minecraft':'26.3','class':'ServerPlayerGameMode','methods':found,'proprietary_code_exported':False}
Path('probes/active4x/two-rivers-d3-handler-shape.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps(report))
if not all(found.values()): raise SystemExit(2)
PY
