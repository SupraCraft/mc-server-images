#!/usr/bin/env bash
set -euo pipefail

: "${MC_VERSION:?MC_VERSION is required}"
: "${MC_SERVER_URL:?MC_SERVER_URL is required}"
: "${MC_SERVER_SHA256:?MC_SERVER_SHA256 is required}"

mkdir -p /data/.runtime /data/world/datapacks/supracraft_active4x

jar=/data/.runtime/server.jar
if [[ ! -f "$jar" ]] || ! echo "$MC_SERVER_SHA256  $jar" | sha256sum -c - >/dev/null 2>&1; then
  tmp="$jar.tmp"
  rm -f "$tmp"
  curl -fsSL "$MC_SERVER_URL" -o "$tmp"
  echo "$MC_SERVER_SHA256  $tmp" | sha256sum -c -
  mv "$tmp" "$jar"
fi

rm -rf /data/world/datapacks/supracraft_active4x/*
cp -a /opt/supracraft/datapack/. /data/world/datapacks/supracraft_active4x/

cat > /data/eula.txt <<'EOF'
eula=true
EOF

cat > /data/server.properties <<'EOF'
online-mode=false
white-list=false
enforce-whitelist=false
server-port=25565
view-distance=3
simulation-distance=3
spawn-protection=0
max-players=8
enable-rcon=false
enable-query=false
generate-structures=false
level-name=world
level-seed=4242424242
level-type=minecraft:flat
generator-settings={"biome":"minecraft:plains","features":false,"lakes":false,"layers":[{"block":"minecraft:bedrock","height":1},{"block":"minecraft:dirt","height":2},{"block":"minecraft:grass_block","height":1}],"structure_overrides":[]}
motd=SupraCraft Two Rivers D2A staging
EOF

exec java -Xms512M -Xmx1536M -jar "$jar" nogui
