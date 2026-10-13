#!/usr/bin/env bash
set -euo pipefail
work="${RUNNER_TEMP:-/tmp}/mc-stack-s1"
rm -rf "$work"; mkdir -p "$work"; cd "$work"
vc_url="https://github.com/SupraCraft/VanillaCord/releases/download/v2.9.0/supracraft-vanillacord-2.9.0.jar"
vc_sha="24e850a261dbf108e2f7ac412c34651ffae753543665ec47d5e40ff9c8981719"
vc_http="$(curl -fsSL --connect-timeout 15 --max-time 120 \
  -w 'http=%{http_code} type=%{content_type} bytes=%{size_download}' \
  "$vc_url" -o vanillacord.jar)"
printf 'PUBLIC_RELEASE_DOWNLOAD %s\n' "$vc_http"
printf 'PUBLIC_RELEASE_ACTUAL_SHA256 %s\n' "$(sha256sum vanillacord.jar | cut -d' ' -f1)"
printf 'PUBLIC_RELEASE_FILE_BYTES %s\n' "$(wc -c < vanillacord.jar)"
printf 'PUBLIC_RELEASE_SIGNATURE_HEX %s\n' "$(head -c 4 vanillacord.jar | od -An -tx1 | tr -d '[:space:]')"
# No bypass. Fail closed before Java if the public bytes differ from release provenance.
printf '%s  %s\n' "$vc_sha" vanillacord.jar | sha256sum -c -
mkdir -p "$work/server"
java -jar "$work/vanillacord.jar" 26.3
patched="$(find out -type f -name '26.3.jar' | head -1)"
test -s "$patched"
cp "$patched" "$work/server/server.jar"
cd "$work/server"
printf 'eula=true\n' > eula.txt
cat > server.properties <<'EOF'
online-mode=false
enforce-secure-profile=false
network-compression-threshold=-1
server-port=25565
motd=SupraCraft S1
EOF
cat > vanillacord.txt <<'EOF'
version = 2.0
forwarding = velocity
seecret = s1-public-ci-nonsecret
EOF
boot() {
  java -Xms512M -Xmx1024M -jar server.jar --nogui >server.log 2>&1 &
  pid=$!
  for i in $(seq 1 120); do
    grep -q 'Done (' server.log && break
    kill -0 "$pid" 2>/dev/null || { cat server.log; return 1; }
    sleep 1
  done
  grep -q 'Done (' server.log
  test -f world/level.dat
  kill -TERM "$pid"
  wait "$pid" || true
}
boot
test -f world/level.dat
first="$(stat -c '%s' world/level.dat)"
boot
test -f world/level.dat
second="$(stat -c '%s' world/level.dat)"
test "$first" -gt 0
test "$second" -gt 0
printf 'PASS S1 vanilla+VanillaCord exact-26.3 boot/restart world persistence first=%s second=%s\n' "$first" "$second"
