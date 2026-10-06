#!/usr/bin/env bash
set -euo pipefail
work="${RUNNER_TEMP:-/tmp}/mc-stack-s1"
rm -rf "$work"; mkdir -p "$work"; cd "$work"
git clone https://github.com/SupraCraft/VanillaCord.git vanillacord
cd vanillacord
git checkout ae95c0e64c4b867a60909b71bd2eb8d17051a5e5
./mvnw -B verify
jar="$(find artifacts target -type f -name 'supracraft-vanillacord-*.jar' 2>/dev/null | head -1)"
test -n "$jar"
mkdir -p "$work/server"
java -jar "$jar" 26.3
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
