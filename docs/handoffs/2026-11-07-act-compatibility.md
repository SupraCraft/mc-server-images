# Local GitHub Actions compatibility assessment — 2026-11-07

Status: assessment only; no local workflow execution. Public GHA remains the
preferred authoritative runner after the reported monthly minute reset.

## Observed environment

- Installed `act` v0.2.89. `act -l` enumerates repository workflows and jobs.
- `act` warns no valid Docker connection. Docker CLI context is `truenas`,
  targeting unreachable `tcp://truenas.local:2375`; no local engine responds.
- `act -W .github/workflows/minecraft-hosting-stack-contract.yml -j contract
  -n` did not produce a dry-run plan: without a Docker daemon, this act version
  entered an interactive default runner-image prompt and failed in the
  noninteractive shell. No image was downloaded and no job started.
- No `.actrc`, local `act` secrets file, or emulator configuration was added.
- Latest public operational run [42369731805](https://github.com/SupraCraft/mc-server-images/actions/runs/42369731805)
  is scheduled metadata discovery on main `0e9033031d16010ca4b69589c778d6de8152261f`;
  `paper-26-3` and `velocity-4-2` were skipped by design.

## Fit and boundary

After a supported local Docker engine is available, first assess these jobs:

1. `minecraft-hosting-stack-contract` — Python schema/static validation.
2. `world-activation-transaction` — Python contract validation.
3. `rcon-adapter` — Python packet/mock loopback tests; requires current
   interpreter path and local TCP loopback.

These short jobs are useful local checks. Use explicit workflow selection,
document runner image sizes, pin any `act` cache/config in the user's local
profile only after review, and execute one job at a time. Do not expose secrets
or dispatch physical/native workflows through local `act`.

Do not count `act` as GitHub-hosted runner acceptance. GitHub context and token
permissions, service/network behavior, artifact upload/download, runtime
actions, and hosted runner image differ. Jobs using `setup-java`, Node,
download/upload artifacts, nested VMs, or product downloads need explicit
compatibility checks and often remain hosted-only. If no local Docker engine
is intended, defer `act` support and rely on cheap source checks plus the
preferred public GHA lane after its allowance resets.

## Next step

Owner decides whether to provide a local Docker endpoint for a bounded spike or
defer local execution. In either case, keep public GHA as the preferred path
for accepted runtime receipts and spend restored minutes only on admitted,
nonduplicative jobs.
