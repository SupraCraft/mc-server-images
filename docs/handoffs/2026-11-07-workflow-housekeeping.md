# Workflow housekeeping continuation, 2026-11-07

Status: local source candidate; no hosted execution or remote integration.
Owner DLE: [Server Images #53](https://github.com/SupraCraft/mc-server-images/issues/53).

## Completed source batches

Starting from `91e60705513d0bf48b25cceb1220795eece2856e`, three independent
disjoint commits migrate the remaining 17 H19 pinned checkout/upload
workflows: six runtime/proxy, seven world-lifecycle and four Mineflayer
fixtures. Exactly 41 substitutions (24 checkout, 17 upload); reverse pin
substitution reproduces original bytes. Commands, events, permissions and
artifact names/paths/retention remain unchanged. Original batch commits:
`bebba62587001c09c77df99835e7190d196d2380`,
`3d34edcf017cff0a59c6d79b68c4f37b3992deae`,
`a98b719ada10cc53c4fe9eae98cb03f4c71b6ad0`.

RCON and world-activation contract workflows now use ubuntu-24.04,
five-minute timeouts, separate per-ref noncancelling concurrency groups,
immutable Node24 checkout and disabled persisted checkout credentials.
Their events, read-only permissions and probe commands remain unchanged.
Independent execution exposed a hardcoded `python3` child command in the
RCON mock, failing Windows with exit 9009. Using `sys.executable` fixes the
fixture without changing its loopback protocol or command-order assertions.

All 37 complete workflows pass actionlint 1.7.12 (shellcheck unavailable and
disabled). Combined local Linux suite: 100 passed, zero skips. Windows:
85 passed, 15 explicit capability skips, zero failures/errors. Both RCON
probes and hosting/world-activation validators pass; independent review of
the lightweight workflow and interpreter changes found no blocking issue.
Linux verification used a temporary native clone, subsequently removed.

## Exact residual inventory and next batches

The committed [source audit](../evidence/workflow-source-audit-2026-11-07.json)
binds 37 workflow Git blobs at source `2bd63b9d7a31b6b1effb98e4363741df0e3ace23`
to 11 distinct first-party action references. Mutable refs were resolved to
exact commits before fetching action manifests; recorded Git blobs and
SHA256 values support independent readback. This is a source snapshot,
not proof of hosted runtime behavior. Current main is unchanged.

| Remaining work | Exact candidate exposure / acceptance gate |
| --- | --- |
| Remote source integration and hosted verification | All local candidates; admission and independent review still required |
| setup-node migration | Six pinned and 13 mutable-v4 occurrences still run Node20; review major-version cache defaults before replacement |
| setup-python migration | Seven mutable-v5 occurrences still run Node20; preserve interpreter version/architecture/cache behavior |
| upload migration in older fixture workflows | Eleven mutable-v4 occurrences still run Node20; verify archive/download contract before replacement |
| Immutable pinning | Six distinct mutable refs remain: checkout v5, setup-java v5, setup-node v4, setup-python v5/v6, upload-artifact v4 |
| Native/identity/client worksets | Separate existing owners and scoped acceptance; no implied progress from metadata or static CI |

Zero candidate jobs lack timeouts. Nine workflows lack top-level
concurrency; absence alone is not a defect. Triage:

- `minecraft-hosting-stack-contract` and `minecraft-stack-s5`: cheap read-only
  checks; no corrective concurrency change required by this audit.
- `export-core-restoration-artifact-26-3`: retain complete artifact custody;
  consider noncancelling serialization only with its producer's next change.
- `26.3-block-catalog`, `datapack-presence-chain-26.3`,
  `minecraft-next-snapshot-canary`, `minecraft-stack-s1`,
  `qualify-velocity-paper-263-link`, `vanilla-runtime-smoke`: review resource
  placement with their next admitted native run. Per-ref concurrency does
  not replace shared heavyweight admission; do not auto-cancel first-failure
  evidence for cosmetic consistency.

## Housekeeping and baton

Keep main at its original clean SHA. Retain scoped local commits and the
combined `fix/workflow-housekeeping-20261107` branch; remove clean temporary
worktrees after owner/coordinator receipts. Local Git custody is not remote
durability. No source push, new PR, merge, hosted dispatch/private minutes,
release or physical APPLY was performed. Continue with bounded major-action
compatibility review, then separately admitted source integration/execution.
