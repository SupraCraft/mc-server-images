FROM eclipse-temurin:25-jre-jammy

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY deploy/active4x-two-rivers/d2a/server-entrypoint.sh /opt/supracraft/server-entrypoint.sh
COPY deploy/active4x-two-rivers/d2a/datapack /opt/supracraft/datapack

RUN chmod +x /opt/supracraft/server-entrypoint.sh

WORKDIR /data
EXPOSE 25565
ENTRYPOINT ["/opt/supracraft/server-entrypoint.sh"]
