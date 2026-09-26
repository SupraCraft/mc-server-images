# mc-server-images

Public reusable Minecraft server runtime images for SupraCraft development,
qualification, and deployment.

## Scope

This repository owns generic server runtime images only.

It does **not** own:

- VIP authentication logic;
- bot logic;
- presentation logic;
- worlds;
- secrets;
- product-specific configuration.

Consumers inject plugins/configuration at runtime.

## Paper runtime

Initial qualified target:

- Minecraft/Paper: 26.2
- Paper stable server build: 123
- Java: 25
- runtime user: uid/gid 10001
- state volume: `/data`

The image refuses to start unless `EULA=TRUE` is explicitly supplied.

### Local shape

```bash
docker run --rm \
  -e EULA=TRUE \
  -e ONLINE_MODE=false \
  -p 25565:25565 \
  ghcr.io/supracraft/mc-server-images/paper:26.2-123
```

Qualification tags are immutable build-specific tags. Product repositories should
pin a qualified tag or digest rather than `latest`.

## Design

The image contains only the pinned Paper runtime. Server state is written under
`/data`; plugins can be mounted under `/data/plugins`.

This lets the same image serve:

- public GitHub Actions qualification;
- private GARM runners;
- local Docker/Compose RDTE;
- later TrueNAS App materialization.
