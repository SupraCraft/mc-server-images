# Current operations and next-release qualification

**Owner:** [SupraCraft Minecraft operational runtime #68](https://github.com/SupraCraft/mc-server-images/issues/68)

This is the active critical path, replacing the historical Paper 1.21.11/TrueNAS app fixture as the product target. Source of machine policy: [spec/operational-runtime-lanes-v1.json](../spec/operational-runtime-lanes-v1.json). The TrueNAS fixture is a regression/Foundry adapter qualification only, never an operational deployment acceptance.

**Status reconciled 2026-11-07:** component S1–S5 runtime/gameplay mechanics have scoped public CI receipts; complete managed operational release acceptance remains **OPEN**. This policy is not evidence that an end-to-end supported deployment has been assembled or promoted.

## Target and evidence gates

| Lane | Exact target | Independent initial oracle | Follow-on integration |
| --- | --- | --- | --- |
| Vanilla authoritative | Minecraft Java 26.3, Java 25, protocol 777, existing pinned server SHA-256 | Official runtime/status receipt plus scoped real player, proxy-transparency and world-agent receipts #86/#87/#89/#90 | Managed Two Rivers deployment, COLLAGE/Gym integration, online identity and native guest remain open |
| Paper optional backend | Minecraft/Paper 26.3; approved build 177 SHA-256 `580c266b6526bb34752e9c2c274be025f763af1ce5b3fa662fa2b3006f966c13` | S4 direct/proxied causal gameplay PASS, #88, run [38471052681](https://github.com/SupraCraft/mc-server-images/actions/runs/38471052681) | Current stable release/build re-resolution, optional identity/admission and native managed deployment remain separate |
| Velocity ingress | Velocity **4.2.0** official release build **30**, SHA-256 `35a5596a5468a035d8a32c8de5ebb0dc6b8d8f0cc3ff5169d514aca762af8aa8` | Standalone boot and proxy status-link receipts; real Paper and VanillaCord forwarding/player-path checks in #86/#88, e.g. [38464663589](https://github.com/SupraCraft/mc-server-images/actions/runs/38464663589) | Authenticated player identity/VIP grant, realm admission and full managed deployment remain open |
| Future release | Minecraft **26.4 snapshot-7** observed 2026-11-07; new official snapshots watched without applying | Daily metadata-only version discovery, non-promotable | Disposable version/protocol/datapack/pack-format canary; independently qualify stable 26.4 on release |

Read-only release discovery uses official Mojang and PaperMC Downloads Service v3 endpoints with a non-generic, attributable User-Agent and strict domains. Its output is **candidate evidence**, not a runtime/compatibility PASS or deploy authorization.

Real runtime smoke jobs are separate and run on PR/push/manual events using public free-tier runners. Daily scheduled jobs perform **only metadata observation** to avoid recurring JAR downloads and private Actions minutes. Receipts preserve exact SHA-256 digests; future promotion must pin the approved artifact digest into a reviewed immutable assembly.

## Dual-track release discipline

- **Operations:** stable released and independently qualified vanilla/Paper/Velocity tuple, world backup, one writer per realm, independent external storage, no automatic upgrades, explicit promotion and rollback. The authoritative Two Rivers gameplay server is vanilla with qualified VanillaCord; Paper remains an adapter/alternative, not a substitute for vanilla semantics.
- **RDTE:** stable compatibility baselines plus 26.4 snapshots canary. Snapshot work may detect packet, datapack, resource-pack, configuration or world-upgrade incompatibilities; it has no operational promotion capability.
- **Major migration hazards already identified:** 26.4 snapshot changes in intention-packet host parameters and custom mod-list payload; datapack format 123 and resource-pack format 100 by snapshot 3; Paper anticipates consolidated Bukkit/Spigot/Paper configuration. These are explicit negative/compatibility tests, not reasons to copy old configuration blindly.
- **All audiences:** humans, automation and agents submit the same versioned COLLAGE deployment intent, get identical observed plans, and are constrained by separate identity/authority and approval scopes.

## Bring-up ladder and remaining gates

| Gate | Current status | Evidence and remaining work |
| --- | --- | --- |
| S0 contract | PASS, source contract only | Hosting-stack schema and activation transaction validators; not runtime acceptance. |
| S1 vanilla + VanillaCord | PASS, scoped disposable player/runtime checks | Vanilla 26.3/Java25/protocol777; immutable VanillaCord forwarding/player path #86; direct/proxied same-world gameplay #87. No stock Mojang GUI client or real online account claim. |
| S2 Velocity ingress | PASS, scoped runtime and forwarding checks | Velocity4.2.0 build30; Paper and VanillaCord proxy paths. Real account identity, VIP grant/revocation and realm admission remain OPEN. |
| S3 proxy transparency | PASS, scoped | Same-world vanilla direct vs Velocity+VanillaCord gameplay #87. Does not establish managed production topology. |
| S4 Paper adapter | PASS, scoped to approved Paper26.3 build177 | Direct/proxied causal gameplay #88. Re-resolve current approved stable build before any new release tuple; no auto-upgrade. |
| S5 world-agent mechanics | PASS, scoped disposable vanilla lifecycle/fault rollback | #89; synthetic player/operator datapack rollback #90. Full Two Rivers/COLLAGE/Gym-managed operation remains OPEN. |
| S6 Foundry materialization | PARTIAL | OCI Java25 vanilla26.3 and native TrueNAS source/control producer-to-consumer admission are qualified by historical #83–#85 and DLE receipts. Current native guest lifecycle is not accepted. |
| S7 native TrueNAS disposable App | OPEN | Existing 25.04.2.6 request/source admission is not a guest run. Need a freshly authorized current-game guest, provider readback, independent world persistence, lifecycle and zero-residue cleanup. |
| S8 physical TrueNAS HIL | HOLD | Physical APPLY remains explicitly held. |
| Release integration | OPEN | No current combined managed build/smoke joins exact runtime, identity, storage, gameplay, rollback and cleanup into one release receipt. |
| 26.4 canary | OBSERVE ONLY | Latest main scheduled workflow is metadata-only; run [42369731805](https://github.com/SupraCraft/mc-server-images/actions/runs/42369731805), head `0e9033031d16010ca4b69589c778d6de8152261f`; Paper/Velocity jobs skipped by schedule. No promotion. |

Physical TrueNAS APPLY remains on HOLD. Never re-use earlier Paper 1.21.11/protocol 774 receipts as evidence for Paper or vanilla 26.3/protocol 777.

**Known accepted vanilla source artifact:** `probes/26.3-vanilla-runtime-smoke.json` (protocol 777, Java 25, JAR SHA-256 `d052f14d7a173734fba553711e5b570162e2f2a313267ee31a21b975a679be64`). Paper and Velocity component receipts exist as listed above; they do not equal selection or acceptance of a complete operational tuple.

## CI execution and local compatibility

Public GitHub Actions remains the preferred CI venue. The latest main operational workflow is metadata-only and skips Paper/Velocity runtime jobs. This repository is public; standard `ubuntu-24.04` runs are free independently of the private-repository monthly allowance ([GitHub billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)). The earlier blanket monthly-wait assumption is superseded: bounded public source checks can proceed, while heavyweight or native execution still needs its own admission. Larger runners and artifact/cache storage have separate billing constraints. The locally installed `act` v0.2.89 lists workflows, but execution is unavailable through the configured Docker endpoint. Prefer the admitted public source-check lane; local emulation does not establish hosted runner compatibility.

The candidate workflow housekeeping and portability changes are remotely published in [draft PR110](https://github.com/SupraCraft/mc-server-images/pull/110), with action-compatibility and review fixes stacked through [PR115](https://github.com/SupraCraft/mc-server-images/pull/115). Public main has not received them. Historical local verification at `cd24bf3` is retained in [the workflow handoff](handoffs/2026-11-07-workflow-housekeeping.md); current PR heads and DLE receipts supersede local-only custody claims. Source verification does not establish release acceptance.
