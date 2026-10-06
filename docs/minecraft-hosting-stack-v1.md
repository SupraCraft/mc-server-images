# Minecraft hosting stack v1

Authority: SupraCraft/mc-server-images#53.

## Decision
Use Foundry to materialize a Docker Compose hosting stack. Keep world release, migration, promotion, and game semantics outside Foundry and outside the stack.

The stack exposes Velocity as the player ingress. Vanilla backends use SupraCraft VanillaCord; Paper is an independently qualified adapter. Two Rivers continues to use exact vanilla as its semantic authority.

An optional world-agent is a narrow mechanism sidecar, not a control panel. It may coordinate safe server quiescence and filesystem-facing operations but receives no Docker socket and owns no release policy.

## World-management primitive harvest
Reuse the RCON save/quiesce/resume pattern proven by docker-mc-backup. Use provider acceleration such as ZFS snapshot/clone through an external TrueNAS adapter. Borrow lifecycle vocabulary from Multiverse and asynchronous transfer/status patterns from MCSManager. Do not introduce Crafty, MCSManager, Pterodactyl, or another panel as a second runtime authority.

## Deployment split
Foundry: materialize/wire/health the stack and attach storage.
World controller: external policy and DLE lineage for releases, candidates, migrations, qualification, promotion, rollback, and receipts.
World-agent: optional least-authority mechanism endpoint colocated with a backend.
SupraCraft/Two Rivers: authored content and gameplay semantics.

## Promotion rule
No layer inherits evidence from another. Paper cannot satisfy vanilla qualification. Proxy-path success cannot replace a direct-backend oracle. Nested TrueNAS RDTE cannot claim physical-HIL acceptance.
