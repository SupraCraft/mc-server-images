#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/tmp/supracraft-prismarine-viewer-26.3}"
EXACT_RUNTIME="${2:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_REPO="https://github.com/PrismarineJS/prismarine-viewer.git"
UPSTREAM_SHA="7fa43a7317467a3ba84f857ba6b1ca9597c72b8c"
SRC="$ROOT/src/prismarine-viewer"
LOCAL_NODE_MODULES="$ROOT/local-node_modules"
PATCH_DIR="$REPO_ROOT/patches/prismarine-viewer"

rm -rf "$ROOT"
mkdir -p "$ROOT/src" "$LOCAL_NODE_MODULES"

git clone --filter=blob:none --no-checkout "$UPSTREAM_REPO" "$SRC"
git -C "$SRC" fetch --depth=1 origin "$UPSTREAM_SHA"
git -C "$SRC" checkout --detach "$UPSTREAM_SHA"
test "$(git -C "$SRC" rev-parse HEAD)" = "$UPSTREAM_SHA"

for patch in "$PATCH_DIR"/*.patch; do
  echo "checking $(basename "$patch")"
  git -C "$SRC" apply --check "$patch"
  git -C "$SRC" apply "$patch"
done

git -C "$SRC" diff --check

pushd "$SRC" >/dev/null
npm install
npm run lint
node - <<'NODE'
const { getVersion } = require('./viewer/lib/version')
if (getVersion('26.3') !== '26.1') {
  throw new Error('local 26.3 viewer asset bridge did not resolve to 26.1')
}
console.log(JSON.stringify({
  exactClientVersion: '26.3',
  renderAssetVersion: getVersion('26.3')
}, null, 2))
NODE
test -s public/textures/26.1.png
test -s public/blocksStates/26.1.json
test -s public/worldBounds.json
popd >/dev/null

# Runtime composition is deliberately outside the upstream patch queue.
# Viewer resolves dependencies from its own node_modules first, so project the
# already-qualified exact-26.3 data/chunk implementations into this disposable
# local build. This changes dependency composition, not viewer source.
if [[ -z "$EXACT_RUNTIME" ]]; then
  echo "exact 26.3 runtime path is required" >&2
  exit 2
fi
for package in minecraft-data prismarine-chunk; do
  source="$EXACT_RUNTIME/node_modules/$package"
  target="$SRC/node_modules/$package"
  test -d "$source"
  rm -rf "$target"
  cp -a "$source" "$target"
done

pushd "$SRC" >/dev/null
node - <<'NODE'
const mcData = require('minecraft-data')('26.3')
if (!mcData || mcData.version.minecraftVersion !== '26.3') {
  throw new Error('viewer-local minecraft-data does not resolve exact 26.3')
}
const Chunk = require('prismarine-chunk')('26.3')
const chunk = new Chunk()
console.log(JSON.stringify({
  exactDataVersion: mcData.version.minecraftVersion,
  protocolVersion: mcData.version.version,
  dataVersion: mcData.version.dataVersion,
  chunkMinY: chunk.minY,
  chunkWorldHeight: chunk.worldHeight
}, null, 2))
NODE
popd >/dev/null

ln -s "$SRC" "$LOCAL_NODE_MODULES/prismarine-viewer"

cat > "$ROOT/build-receipt.json" <<EOF
{
  "schema": "supracraft.prismarine-viewer-local-build/v0.1",
  "upstream_repository": "PrismarineJS/prismarine-viewer",
  "upstream_sha": "$UPSTREAM_SHA",
  "patches": [
    "0001-local-26.3-use-26.1-render-assets.patch"
  ],
  "node_major": 24,
  "lint": "passed",
  "generated_assets_verified": [
    "public/textures/26.1.png",
    "public/blocksStates/26.1.json",
    "public/worldBounds.json"
  ],
  "semantic_client_version": "26.3",
  "presentation_asset_version": "26.1",
  "runtime_composition": {
    "minecraft-data": "exact_26.3_qualified_runtime",
    "prismarine-chunk": "exact_26.3_qualified_runtime"
  },
  "support_claim": "local_diagnostic_bridge_only"
}
EOF

echo "$LOCAL_NODE_MODULES"
