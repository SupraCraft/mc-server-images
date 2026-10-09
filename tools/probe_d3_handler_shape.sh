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
javap -p -c -classpath "$d/inner.jar" net.minecraft.server.level.ServerPlayerGameMode > "$d/bytecode.txt"
python3 - "$d/methods.txt" "$d/bytecode.txt" <<'PY'
import json, re, sys
from pathlib import Path
t=Path(sys.argv[1]).read_text()
bytecode=Path(sys.argv[2]).read_text()
refs=('incrementDestroyProgress','destroyAndAck','destroyBlock','getDestroyProgress',
      'blockActionRestricted','mayInteract','canDestroyBlock','hasDelayedDestroy',
      'isDestroyingBlock','isWithinBlockInteractionRange','isUnderSpawnProtection',
      'getMainHandItem','getDestroySpeed','isCreative')
def method_metadata(name):
    lines=bytecode.splitlines()
    start=next((i for i,line in enumerate(lines) if
        (' '+name+'(' in line) and line.strip().endswith(';')),None)
    if start is None:
        return {'found':False}
    end=next((i for i in range(start+1,len(lines)) if
        ('(' in lines[i] and lines[i].strip().endswith(';') and
         lines[i].startswith('  '))),len(lines))
    block='\\n'.join(lines[start:end])
    return {'found':True,'references':{v:v in block for v in refs},
            'uses_0_7_float':('0.7f' in block),
            'conditional_branches':len(re.findall(r'(?m)^\\s*\\d+:\\s+if\\w+',block))}
methods=['tick','handleBlockBreakAction','incrementDestroyProgress','destroyAndAck','destroyBlock','abortDestroyBlock']
found={m:bool(re.search(r'\b'+m+r'\s*\(',t)) for m in methods}
report={'schema':'supracraft.d3-handler-shape/v0.2','minecraft':'26.3','class':'ServerPlayerGameMode','methods':found,'method_decisions':{v:method_metadata(v) for v in ('handleBlockBreakAction','tick','incrementDestroyProgress','destroyAndAck','destroyBlock')},'proprietary_code_exported':False}
Path('probes/active4x/two-rivers-d3-handler-shape.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps(report))
if not all(found.values()): raise SystemExit(2)
PY
