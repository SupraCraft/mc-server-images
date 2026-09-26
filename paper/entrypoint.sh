#!/usr/bin/env sh
set -eu

case "${EULA:-}" in
  TRUE|true|1|yes|YES)
    printf 'eula=true\n' > /data/eula.txt
    ;;
  *)
    echo "EULA must be explicitly accepted with EULA=TRUE" >&2
    exit 64
    ;;
esac

if [ ! -f /data/server.properties ]; then
  cat > /data/server.properties <<EOF
online-mode=${ONLINE_MODE:-true}
server-port=${SERVER_PORT:-25565}
motd=${MOTD:-SupraCraft Paper Runtime}
enable-rcon=false
enable-query=false
spawn-protection=0
EOF
fi

exec java ${JAVA_OPTS:-} -jar /opt/minecraft/paper.jar --nogui
