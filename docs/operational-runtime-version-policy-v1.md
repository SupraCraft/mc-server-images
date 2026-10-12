# Current operations and next-release qualification

**Owner:** [SupraCraft Minecraft operational runtime #68](https://github.com/SupraCraft/mc-server-images/issues/68)

This is the active critical path, replacing the historical Paper 1.21.11/TrueNAS app fixture as the product target. Source of machine policy: [spec/operational-runtime-lanes-v1.json](../spec/operational-runtime-lanes-v1.json). The TrueNAS fixture is a regression/Foundry adapter qualification only, never an operational deployment acceptance.

## Target and evidence gates

| Lane | Exact target | Independent initial oracle | Follow-on integration |
| --- | --- | --- | --- |
| Vanilla authoritative | Minecraft Java 26.3, Java 25, protocol 777, existing pinned server SHA-256 | Already booted in disposable runner, official server+status receipt `probes/26.3-vanilla-runtime-smoke.json` | VanillaCord, Velocity forwarding, safe independent-world hosting, Two Rivers/Gym |
| Paper optional backend | Minecraft/Paper 26.3; resolve official **STABLE** build and record JAR SHA-256, never latest tag at startup | Public Actions standalone Java 25 boot, protocol 777, world `level.dat`, clean stop | Separate Velocity/Paper forwarding and native TrueNAS App qualification |
| Velocity ingress | Velocity **4.2.0** official release build **30**, digest to be pinned after real acquisition | Public Actions standalone Java 25 proxy/listener startup | Verified modern forwarding, offline backend denial, realm-bound VIP admission |
| Future release | Minecraft **26.4 snapshot-3** currently observed; new official snapshots watched without applying | Daily metadata-only version discovery, non-promotable | Disposable version/protocol/datapack/pack-format canary; independently qualify stable 26.4 on release |

Read-only release discovery uses official Mojang and PaperMC Downloads Service v3 endpoints with a non-generic, attributable User-Agent and strict domains. Its output is **candidate evidence**, not a runtime/compatibility PASS or deploy authorization.

Real runtime smoke jobs are separate and run on PR/push/manual events using public free-tier runners. Daily scheduled jobs perform **only metadata observation** to avoid recurring JAR downloads and private Actions minutes. Receipts preserve exact SHA-256 digests; future promotion must pin the approved artifact digest into a reviewed immutable assembly.

## Dual-track release discipline

- **Operations:** stable released and independently qualified vanilla/Paper/Velocity tuple, world backup, one writer per realm, independent external storage, no automatic upgrades, explicit promotion and rollback. The authoritative Two Rivers gameplay server is vanilla with qualified VanillaCord; Paper remains an adapter/alternative, not a substitute for vanilla semantics.
- **RDTE:** stable compatibility baselines plus 26.4 snapshots canary. Snapshot work may detect packet, datapack, resource-pack, configuration or world-upgrade incompatibilities; it has no operational promotion capability.
- **Major migration hazards already identified:** 26.4 snapshot changes in intention-packet host parameters and custom mod-list payload; datapack format 123 and resource-pack format 100 by snapshot 3; Paper anticipates consolidated Bukkit/Spigot/Paper configuration. These are explicit negative/compatibility tests, not reasons to copy old configuration blindly.
- **All audiences:** humans, automation and agents submit the same versioned COLLAGE deployment intent, get identical observed plans, and are constrained by separate identity/authority and approval scopes.

## Minimum S1–S8 remaining

1. Source version candidate/digest resolve and independent stable Paper/Velocity stand-alone boot. Never treat source candidate `DISCOVERED` as PASS.
2. Vanilla 26.3 + VanillaCord + Velocity 4.2.0 exact builds/digests, real login/forwarding, no backend bypass and signed forwarding key handling, plus Paper optional separated lane.
3. Consume the already generated **real** 26.3 restoration datapack and eventually complete MCWORLD/Two Rivers artifacts through COLLAGE with stable world identity, stage/hash/quiesce/snapshot/activate/resume, independent gameplay oracles and failed-activation restore receipt.
4. Materialize newly qualified current-generation products as independently operable native TrueNAS Apps through the disposable Foundry path; do not let TrueNAS catalog app version (e.g., 1.15.30) masquerade as game/server version. Controller failure must not stop standalone games.
5. Qualify 26.4 snapshots in RDTE for source/protocol/content and flag compatibility differences. Once an official stable release exists, repeat the same exact digest and runtime gates before operational release consideration.

Physical TrueNAS APPLY remains on HOLD. Never re-use earlier Paper 1.21.11/protocol 774 receipts as evidence for Paper or vanilla 26.3/protocol 777.

**Known accepted vanilla source artifact:** `probes/26.3-vanilla-runtime-smoke.json` (protocol 777, Java 25, JAR SHA-256 `d052f14d7a173734fba553711e5b570162e2f2a313267ee31a21b975a679be64`). New Paper and Velocity runtime receipts are pending their own public CI, and are not yet operationally approved.
