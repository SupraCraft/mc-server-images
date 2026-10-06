FROM node:24-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git python3 python-is-python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY tools/install_experimental_prismarine_26_3.sh /src/tools/install_experimental_prismarine_26_3.sh
COPY tools/apply_mineflayer_tick_end_26_3.py /src/tools/apply_mineflayer_tick_end_26_3.py
COPY probes/mineflayer-runtime /src/probes/mineflayer-runtime

RUN chmod +x /src/tools/install_experimental_prismarine_26_3.sh \
    && /src/tools/install_experimental_prismarine_26_3.sh /opt/prismarine

ENV NODE_PATH=/opt/prismarine/runtime/node_modules
WORKDIR /app
COPY deploy/active4x-two-rivers/d2b/actor_service.js /app/actor_service.js

VOLUME ["/actor-state"]
CMD ["node", "/app/actor_service.js"]
