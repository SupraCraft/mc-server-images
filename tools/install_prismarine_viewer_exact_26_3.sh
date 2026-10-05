#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/tmp/supracraft-prismarine-viewer-exact-26.3}"
EXACT_RUNTIME="${2:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

VIEWER_REPO="https://github.com/PrismarineJS/prismarine-viewer.git"
VIEWER_SHA="7fa43a7317467a3ba84f857ba6b1ca9597c72b8c"
EXTRACTOR_REPO="https://github.com/PrismarineJS/minecraft-jar-extractor.git"
EXTRACTOR_SHA="dddd4cf9e2a33186753c6ebdeb87c13c04ef7589"

SRC="$ROOT/src/prismarine-viewer"
EXTRACTOR="$ROOT/src/minecraft-jar-extractor"
GENERATED="$ROOT/generated-assets"
TEMP="$ROOT/minecraft-client"
LOCAL_NODE_MODULES="$ROOT/local-node_modules"
PATCH="$REPO_ROOT/patches/prismarine-viewer-exact/0001-admit-exact-26.3-render-assets.patch"

if [[ -z "$EXACT_RUNTIME" ]]; then
  echo "exact 26.3 runtime path is required" >&2
  exit 2
fi

rm -rf "$ROOT"
mkdir -p "$ROOT/src" "$LOCAL_NODE_MODULES"

git clone --filter=blob:none --no-checkout "$VIEWER_REPO" "$SRC"
git -C "$SRC" fetch --depth=1 origin "$VIEWER_SHA"
git -C "$SRC" checkout --detach "$VIEWER_SHA"
test "$(git -C "$SRC" rev-parse HEAD)" = "$VIEWER_SHA"

pushd "$SRC" >/dev/null
npm install
npm run lint
popd >/dev/null

for package in minecraft-data prismarine-chunk; do
  source="$EXACT_RUNTIME/node_modules/$package"
  target="$SRC/node_modules/$package"
  test -d "$source"
  rm -rf "$target"
  cp -a "$source" "$target"
done

git clone --filter=blob:none --no-checkout "$EXTRACTOR_REPO" "$EXTRACTOR"
git -C "$EXTRACTOR" fetch --depth=1 origin "$EXTRACTOR_SHA"
git -C "$EXTRACTOR" checkout --detach "$EXTRACTOR_SHA"
test "$(git -C "$EXTRACTOR" rev-parse HEAD)" = "$EXTRACTOR_SHA"

pushd "$EXTRACTOR" >/dev/null
npm install
rm -rf node_modules/minecraft-data
cp -a "$EXACT_RUNTIME/node_modules/minecraft-data" node_modules/minecraft-data
node - <<'NODE'
const data = require('minecraft-data')('26.3')
if (!data || data.version.minecraftVersion !== '26.3') {
  throw new Error('extractor-local minecraft-data does not resolve exact 26.3')
}
console.log(JSON.stringify({
  minecraftVersion: data.version.minecraftVersion,
  protocolVersion: data.version.version,
  dataVersion: data.version.dataVersion
}, null, 2))
NODE
node image_names.js 26.3 "$GENERATED" "$TEMP"
popd >/dev/null

ASSETS="$GENERATED/26.3"
test -s "$ASSETS/blocks_states.json"
test -s "$ASSETS/blocks_models.json"
test -d "$ASSETS/blocks"

VIEWER_ROOT="$SRC" ASSETS_ROOT="$ASSETS" node - <<'NODE'
const fs = require('fs')
const path = require('path')

const viewerRoot = process.env.VIEWER_ROOT
const assetsRoot = process.env.ASSETS_ROOT
const { makeTextureAtlas } = require(path.join(viewerRoot, 'viewer/lib/atlas'))
const { prepareBlocksStates } = require(path.join(viewerRoot, 'viewer/lib/modelsBuilder'))
const Chunks = require(path.join(viewerRoot, 'node_modules/prismarine-chunk'))

const assets = {
  directory: assetsRoot,
  blocksStates: JSON.parse(fs.readFileSync(path.join(assetsRoot, 'blocks_states.json'), 'utf8')),
  blocksModels: JSON.parse(fs.readFileSync(path.join(assetsRoot, 'blocks_models.json'), 'utf8'))
}

const atlas = makeTextureAtlas(assets)
const publicRoot = path.join(viewerRoot, 'public')
fs.mkdirSync(path.join(publicRoot, 'textures'), { recursive: true })
fs.mkdirSync(path.join(publicRoot, 'blocksStates'), { recursive: true })
fs.writeFileSync(path.join(publicRoot, 'textures/26.3.png'), atlas.image)
fs.writeFileSync(
  path.join(publicRoot, 'blocksStates/26.3.json'),
  JSON.stringify(prepareBlocksStates(assets, atlas))
)

const boundsPath = path.join(publicRoot, 'worldBounds.json')
const bounds = JSON.parse(fs.readFileSync(boundsPath, 'utf8'))
const chunk = new (Chunks('26.3'))()
bounds['26.3'] = {
  minY: chunk.minY ?? 0,
  worldHeight: chunk.worldHeight ?? 256
}
fs.writeFileSync(boundsPath, JSON.stringify(bounds))

console.log(JSON.stringify({
  textureAtlasBytes: atlas.image.length,
  blockStateCount: Object.keys(assets.blocksStates).length,
  modelCount: Object.keys(assets.blocksModels).length,
  worldBounds: bounds['26.3']
}, null, 2))
NODE

git -C "$SRC" apply --check "$PATCH"
git -C "$SRC" apply "$PATCH"
git -C "$SRC" diff --check

pushd "$SRC" >/dev/null
npm run lint
node - <<'NODE'
const fs = require('fs')
const { getVersion } = require('./viewer/lib/version')
const mcData = require('minecraft-data')('26.3')
if (getVersion('26.3') !== '26.3') {
  throw new Error('viewer does not select exact 26.3 assets')
}
if (!mcData || mcData.version.minecraftVersion !== '26.3') {
  throw new Error('viewer-local minecraft-data lost exact 26.3')
}
for (const file of ['public/textures/26.3.png', 'public/blocksStates/26.3.json', 'public/worldBounds.json']) {
  if (!fs.statSync(file).size) throw new Error('empty generated artifact: ' + file)
}
console.log(JSON.stringify({
  exactClientVersion: '26.3',
  renderAssetVersion: getVersion('26.3'),
  textureAtlasBytes: fs.statSync('public/textures/26.3.png').size,
  blockStatesBytes: fs.statSync('public/blocksStates/26.3.json').size
}, null, 2))
NODE
popd >/dev/null

ln -s "$SRC" "$LOCAL_NODE_MODULES/prismarine-viewer"

cat > "$ROOT/build-receipt.json" <<EOF
{
  "schema": "supracraft.prismarine-viewer-local-build/v0.2",
  "viewer_upstream_repository": "PrismarineJS/prismarine-viewer",
  "viewer_upstream_sha": "$VIEWER_SHA",
  "extractor_upstream_repository": "PrismarineJS/minecraft-jar-extractor",
  "extractor_upstream_sha": "$EXTRACTOR_SHA",
  "patches": [
    "0001-admit-exact-26.3-render-assets.patch"
  ],
  "node_major": 24,
  "lint": "passed",
  "semantic_client_version": "26.3",
  "presentation_asset_version": "26.3",
  "runtime_composition": {
    "minecraft-data": "exact_26.3_qualified_runtime",
    "prismarine-chunk": "exact_26.3_qualified_runtime"
  },
  "asset_source": "ephemeral_official_26.3_client_extraction",
  "asset_retention": "derived_viewer_atlas_and_blockstates_only_in_disposable_build",
  "support_claim": "local_exact_26.3_qualification_candidate"
}
EOF

echo "$LOCAL_NODE_MODULES"
