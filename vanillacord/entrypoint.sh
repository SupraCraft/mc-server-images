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

version="${MINECRAFT_VERSION:-26.2}"
runtime_dir="/data/runtime"
server_jar="${runtime_dir}/vanillacord-${version}.jar"
digest_file="${server_jar}.sha256"

mkdir -p "${runtime_dir}"

if [ ! -f "${server_jar}" ]; then
  echo "[materialize] VanillaCord resolving and patching Minecraft ${version}"
  work="$(mktemp -d /data/.vanillacord-materialize.XXXXXX)"
  cleanup() {
    rm -rf "${work}"
  }
  trap cleanup EXIT INT TERM

  (
    cd "${work}"
    java -jar /opt/vanillacord/vanillacord.jar "${version}"
  )

  test -f "${work}/out/${version}.jar"
  mv "${work}/out/${version}.jar" "${server_jar}"
  sha256sum "${server_jar}" | awk '{print $1}' > "${digest_file}"
  cleanup
  trap - EXIT INT TERM
else
  if [ ! -f "${digest_file}" ]; then
    echo "existing VanillaCord runtime lacks materialization digest: ${digest_file}" >&2
    exit 65
  fi
  expected="$(cat "${digest_file}")"
  echo "${expected}  ${server_jar}" | sha256sum -c -
  echo "[materialize] reusing verified VanillaCord runtime ${version}"
fi

if [ ! -f /data/server.properties ]; then
  cat > /data/server.properties <<EOF
online-mode=${ONLINE_MODE:-false}
enforce-secure-profile=false
network-compression-threshold=-1
server-port=${SERVER_PORT:-25565}
motd=${MOTD:-SupraCraft VanillaCord Backend}
enable-rcon=false
enable-query=false
spawn-protection=0
EOF
fi

if [ ! -f /data/vanillacord.txt ]; then
  case "${FORWARDING:-bungeecord}" in
    velocity)
      if [ -z "${FORWARDING_SECRET:-}" ]; then
        echo "FORWARDING_SECRET is required when FORWARDING=velocity" >&2
        exit 66
      fi
      cat > /data/vanillacord.txt <<EOF
version = 2.0
forwarding = velocity
seecret = ${FORWARDING_SECRET}
EOF
      chmod 600 /data/vanillacord.txt
      ;;
    bungeeguard)
      if [ -z "${FORWARDING_SECRET:-}" ]; then
        echo "FORWARDING_SECRET is required when FORWARDING=bungeeguard" >&2
        exit 66
      fi
      cat > /data/vanillacord.txt <<EOF
version = 2.0
forwarding = bungeeguard
seecret = ${FORWARDING_SECRET}
EOF
      chmod 600 /data/vanillacord.txt
      ;;
    bungeecord)
      cat > /data/vanillacord.txt <<EOF
version = 2.0
forwarding = bungeecord
seecret =
EOF
      ;;
    *)
      echo "unsupported FORWARDING mode: ${FORWARDING}" >&2
      exit 67
      ;;
  esac
fi

exec java ${JAVA_OPTS:-} -jar "${server_jar}" --nogui
