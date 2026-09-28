#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/tmp/supracraft-prismarine-26.3}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$REPO_ROOT/probes/mineflayer-runtime/experimental-stack.json"

rm -rf "$ROOT"
mkdir -p "$ROOT/src" "$ROOT/runtime"

read_component() {
  python - "$MANIFEST" "$1" "$2" <<'PY'
import json, sys
manifest=json.load(open(sys.argv[1],encoding="utf-8"))
print(manifest["components"][sys.argv[2]][sys.argv[3]])
PY
}

clone_exact() {
  local key="$1"
  local dest="$2"
  local repo sha
  repo="$(read_component "$key" repository)"
  sha="$(read_component "$key" sha)"
  git clone --filter=blob:none --no-checkout "https://github.com/$repo.git" "$dest"
  git -C "$dest" fetch --depth=1 origin "$sha"
  git -C "$dest" checkout --detach "$sha"
  test "$(git -C "$dest" rev-parse HEAD)" = "$sha"
}

clone_exact node-minecraft-data "$ROOT/src/node-minecraft-data"
rm -rf "$ROOT/src/node-minecraft-data/minecraft-data"
clone_exact minecraft-data-source "$ROOT/src/node-minecraft-data/minecraft-data"

pushd "$ROOT/src/node-minecraft-data" >/dev/null
npm install --ignore-scripts
npm run generate:data
test -s data.js
node - <<'NODE'
const mcData=require('./')
const d=mcData('26.3')
if (!d) throw new Error('generated node-minecraft-data does not resolve 26.3')
if (d.version.minecraftVersion !== '26.3') throw new Error('wrong minecraft-data version: '+JSON.stringify(d.version))
console.log(JSON.stringify({
  minecraftVersion:d.version.minecraftVersion,
  majorVersion:d.version.majorVersion,
  version:d.version.version,
  dataVersion:d.version.dataVersion
}, null, 2))
NODE
popd >/dev/null

clone_exact minecraft-protocol "$ROOT/src/node-minecraft-protocol"
clone_exact prismarine-chunk "$ROOT/src/prismarine-chunk"
clone_exact mineflayer "$ROOT/src/mineflayer"

python - "$MANIFEST" "$ROOT/runtime/package.json" "$ROOT/src" <<'PY'
import json, pathlib, sys
manifest=json.load(open(sys.argv[1],encoding="utf-8"))
src=pathlib.Path(sys.argv[3]).resolve()
package={
  "name":"supracraft-prismarine-26-3-runtime",
  "private":True,
  "version":"0.0.0",
  "engines":{"node":">=22"},
  "dependencies":{
    "minecraft-data":"file:"+str(src/"node-minecraft-data"),
    "minecraft-protocol":"file:"+str(src/"node-minecraft-protocol"),
    "prismarine-chunk":"file:"+str(src/"prismarine-chunk"),
    "mineflayer":"file:"+str(src/"mineflayer")
  }
}
pathlib.Path(sys.argv[2]).write_text(json.dumps(package,indent=2)+"\n",encoding="utf-8")
PY

pushd "$ROOT/runtime" >/dev/null
npm install --ignore-scripts=false
node - <<'NODE'
const names=['mineflayer','minecraft-data','minecraft-protocol','prismarine-chunk']
const versions={}
for (const name of names) {
  const p=require('./node_modules/'+name+'/package.json')
  versions[name]=p.version
}
const md=require('minecraft-data')('26.3')
if (!md) throw new Error('runtime minecraft-data does not resolve 26.3')
const proto=require('minecraft-protocol')
if (!proto || typeof proto.createClient !== 'function') throw new Error('minecraft-protocol runtime missing createClient')
console.log(JSON.stringify({
  versions,
  minecraftData26_3:{
    minecraftVersion:md.version.minecraftVersion,
    majorVersion:md.version.majorVersion,
    protocolVersion:md.version.version,
    dataVersion:md.version.dataVersion
  }
}, null, 2))
NODE
popd >/dev/null

echo "$ROOT/runtime"
