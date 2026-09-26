# VanillaCord runtime materializer contract

The public image contains:

- Java 25;
- the pinned, SupraCraft-published VanillaCord release;
- materialization/startup tooling.

It contains **no Mojang Minecraft server JAR**.

On first start, VanillaCord:

1. resolves the requested Minecraft version through Mojang's official version manifest;
2. downloads the official server JAR;
3. verifies Mojang's published size and SHA-1;
4. patches the server;
5. writes only the patched runtime to persistent `/data/runtime`;
6. removes the temporary unpatched download.

Subsequent starts verify and reuse the materialized patched runtime.

The image is therefore redistributable without redistributing the Mojang server
artifact itself. The server artifact is acquired by the operator at runtime after
explicit EULA acceptance.

## Proxy forwarding

Supported materialization/runtime modes mirror VanillaCord:

- `bungeecord`;
- `bungeeguard`;
- `velocity`.

Secret-bearing forwarding modes require `FORWARDING_SECRET` and persist the
resulting `vanillacord.txt` under the consumer's `/data` volume, not in the
image.
