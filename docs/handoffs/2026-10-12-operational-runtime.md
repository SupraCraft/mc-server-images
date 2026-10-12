# SupraCraft operational handoff — 2026-10-12

**Primary authority:** [mc-server-images#68](https://github.com/SupraCraft/mc-server-images/issues/68). **COLLAGE consumer acceptance:** [collage-private#3](https://github.com/SupraCraft/collage-private/issues/3). **Hosting topology:** `docs/deployment-model-v1.md`. **World transaction:** `spec/minecraft-world-activation-transaction-v1.json`.

This is a DLE continuity checkpoint, not evidence of an operational release. A new actor must re-read current GitHub heads, issues, and CI rather than assume this snapshot remains current.

## Verified current-generation baseline

| Gate | Independently supported result | Evidence |
| --- | --- | --- |
| Vanilla Java 26.3 | Java 25, protocol 777, real server boot; upstream JAR SHA256 `d052f14d7a173734fba553711e5b570162e2f2a313267ee31a21b975a679be64` | `probes/26.3-vanilla-runtime-smoke.json` |
| Paper 26.3 build 177 | SHA256 `580c266b6526bb34752e9c2c274be025f763af1ce5b3fa662fa2b3006f966c13`; real standalone boot/world/clean stop | [GHA 38283607884](https://github.com/SupraCraft/mc-server-images/actions/runs/38283607884), artifact 11761763863 |
| Velocity 4.2.0 build 30 | SHA256 `35a5596a5468a035d8a32c8de5ebb0dc6b8d8f0cc3ff5169d514aca762af8aa8`; real standalone proxy startup | Same GHA, artifact 11762796254 |
| Velocity → Paper 26.3 | Real pinned two-process loopback: backend status through proxy, backend stop, backend restart/recovery, world continuity | [PR #71](https://github.com/SupraCraft/mc-server-images/pull/71) merged `b6bd90f31425bd698352fe7056b48115b656436c`, [GHA 38284969528](https://github.com/SupraCraft/mc-server-images/actions/runs/38284969528) PASS, artifact 11763007034 |
| Next-release RDTE | 26.4 Snapshot 3 checksum-verified disposable server boot; preview protocol 1073742165; **no operational promotion** | [PR #70](https://github.com/SupraCraft/mc-server-images/pull/70), [GHA 38284070195](https://github.com/SupraCraft/mc-server-images/actions/runs/38284070195), artifact 11762846614 |
| Version policy | [PR #69](https://github.com/SupraCraft/mc-server-images/pull/69), digest-bound `spec/rdte-current-artifact-pins-v1.json`, `spec/operational-runtime-lanes-v1.json`; read-only next-release observation | Main at closeout `b6bd90f31425bd698352fe7056b48115b656436c` |
| World artifact precursor | Real vanilla 26.3 datapack ZIP + source provenance, common human/automation/agent plan/source parity | `mc-server-images#67`; `SupraCraft/collage#21` |

**Non-claims:** Status passthrough does **not** prove player login, modern identity forwarding, authorization, VanillaCord, a full Two Rivers world, gameplay, native TrueNAS or physical HIL. Standalone Paper does not prove vanilla semantics. Snapshot boot does not prove stable 26.4 support.

## Highest READY work and dependencies

1. **OP-1 (top):** Extend exact SHA-pinned Velocity 4.2.0 + Paper 26.3 runner to qualify actual user login, modern player forwarding, denied direct-backend bypass, reconnect and player/realm separation. Use [velocity-identity-private#3](https://github.com/SupraCraft/velocity-identity-private/issues/3) for existing principal/admission authority. Existing offline-loopback status test must **never** be mistaken for an operational authentication topology.
2. **OP-2:** Independently qualify vanilla Minecraft 26.3 + [VanillaCord](https://github.com/SupraCraft/VanillaCord) with Velocity 4.2.0; prove proxy/identity data path and direct-backend denial, rather than inferring from Paper. Source/code work can run in parallel with OP-1; serialize actual shared compute/realm mutation.
3. **OP-3:** Deploy a verified inner datapack ZIP into an actual *disposable vanilla 26.3 world*, using `spec/minecraft-world-activation-transaction-v1.json` for stage/hash/quiesce/snapshot/activate/verify/rollback. Full MCWORLD/Two Rivers story scope follows [mc-structure-foundry-private#19](https://github.com/SupraCraft/mc-structure-foundry-private/issues/19) and independent [Gym#21](https://github.com/SupraCraft/mc-bot-gym-private/issues/21). The GitHub Actions *outer archive* digest is not the inner ZIP's SHA.
4. **OP-4:** After independent current-version runtime gates, qualify host-native TrueNAS App/proxy/world storage in disposable RDTE through Foundry. Do not let TrueNAS catalog App version 1.15.x stand in for Minecraft 26.3. Controller outages must not stop durable independently operable servers.
5. **OP-5:** Keep 26.4 snapshot tests separate and non-promotable. Track protocol, datapack, client/resource format, VanillaCord, Velocity and Paper config differences. An official stable release needs a **new** digest/version contract and complete requalification before any operations promotion.

**Parallel work:** OP-1, OP-2 source evaluation, OP-3 staging primitives and OP-5 compatibility scans. **Sequential:** exact runtime artifacts → current proxy/identity qualification → disposable deployment/world activation → independent causal and client oracles → separate operations approval. Delegating actor owns integration/reconciliation and may use bounded actor mission packages; no child self-promotes its own run.

## Legacy regression is not critical-path authorization

Historical nested TrueNAS 25.04.1, Paper 1.21.11 and App 1.15.29 lifecycle [GHA 38200675099](https://github.com/SemperSupra/agent-dispatch/actions/runs/38200675099) passed *that older runtime only*. COLLAGE native observation P2-002 and P2-003 failed least-authority readback setup; P2-004 failed retired catalog pin. P2-005 [GHA 38278878449](https://github.com/SemperSupra/agent-dispatch/actions/runs/38278878449) **failed cheap consumer-authority contract**, before KVM: no new guest run and no current-version result. Authority [agent-dispatch-private#614](https://github.com/SemperSupra/agent-dispatch-private/issues/614) and [#625](https://github.com/SemperSupra/agent-dispatch-private/issues/625). Do not replay unchanged requests or infer 26.3 readiness.

## Cold-start & governance

Discover workspace and repo access; assume **no local directory, sidecar, or resident actor state**. Reconcile live GitHub heads and the linked DLE authorities before changes. Prefer real public/free-tier qualifications, exact source SHA/build/image digests, machine-readable receipt and independent oracles. Perform discover/observe → plan → admitted disposable apply → verify → record causal evidence, rollback/cleanup, and update issue #68 and consumer #3. Humans, automation and agents share one versioned request/receipt contract, differing only in separately verified authorization and audience interface. Preserve current production worlds: no auto-upgrades/downgrades. **Physical TrueNAS APPLY HOLD**; no private hosted Actions-minute drain. Escalate only genuine authority, permission, unsafe-mutation or material owner-decision blockers.

**Closure:** Current standalone, proxy-status and 26.4 preview baseline PASS; no active guest work required by this session. Resume with OP-1 real player path and OP-2 VanillaCord compatibility before further control-plane expansion.
