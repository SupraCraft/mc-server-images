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

version="${PAPER_VERSION:-26.2}"
build="${PAPER_BUILD:-123}"
runtime_dir="/data/runtime"
server_jar="${runtime_dir}/paper-${version}-${build}.jar"
digest_file="${server_jar}.sha256"
source_file="${server_jar}.source.json"

mkdir -p "${runtime_dir}"

if [ ! -f "${server_jar}" ]; then
  echo "[materialize] resolving Paper ${version} build ${build}"
  response="$(
    curl --fail --silent --show-error \
      -H "User-Agent: ${USER_AGENT}" \
      "https://fill.papermc.io/v3/projects/paper/versions/${version}/builds"
  )"

  row="$(
    printf '%s' "${response}" | jq -cer \
      --argjson build "${build}" \
      'first(.[] | select(.id == $build and .channel == "STABLE"))'
  )"
  url="$(printf '%s' "${row}" | jq -er '.downloads["server:default"].url')"
  sha256="$(printf '%s' "${row}" | jq -er '.downloads["server:default"].checksums.sha256')"
  test "${#sha256}" -eq 64

  tmp="${server_jar}.tmp"
  rm -f "${tmp}"
  curl --fail --location --retry 3 \
    -H "User-Agent: ${USER_AGENT}" \
    "${url}" \
    --output "${tmp}"
  echo "${sha256}  ${tmp}" | sha256sum -c -
  mv "${tmp}" "${server_jar}"
  printf '%s\n' "${sha256}" > "${digest_file}"
  printf '%s\n' "${row}" > "${source_file}"
else
  if [ ! -f "${digest_file}" ]; then
    echo "existing Paper runtime lacks materialization digest: ${digest_file}" >&2
    exit 65
  fi
  expected="$(cat "${digest_file}")"
  echo "${expected}  ${server_jar}" | sha256sum -c -
  echo "[materialize] reusing verified Paper runtime ${version} build ${build}"
fi

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

exec java ${JAVA_OPTS:-} -jar "${server_jar}" --nogui
