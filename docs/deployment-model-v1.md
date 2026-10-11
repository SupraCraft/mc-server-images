# SupraCraft Minecraft server and services deployment model v1

**Status:** accepted architectural intent; implementation and deployment acceptance are independently gated.  
**Product authority:** [mc-server-images#53](https://github.com/SupraCraft/mc-server-images/issues/53).  
**Related decisions:** [hosting-stack-v1](minecraft-hosting-stack-v1.md), [hosting-stack schema](../spec/minecraft-hosting-stack-v1.json), [world activation](../spec/minecraft-world-activation-transaction-v1.json), [COLLAGE hypothesis/falsification](https://github.com/SupraCraft/collage-private/blob/main/research/thesis.md), [Foundry product #288](https://github.com/SemperSupra/truenas-app-foundry-private/issues/288), [native Minecraft RDTE #588](https://github.com/SemperSupra/agent-dispatch-private/issues/588).

## Decision and scope

Deploy **portable, declarative, independently operable Minecraft applications**. Persistent worlds are independently owned assets, not container payloads or disposable App storage. Materialization, fleet composition, world release, and gameplay semantics are separate authorities. TrueNAS Apps/Foundry is the **first provider**, not a semantic dependency. Full-fleet design below is a target, not a claim that every component is currently running or qualified.

**No mandatory COLLAGE controller.** COLLAGE (Composable Orchestration Layer for Lifecycle-Aware Game Environments) is an *optional* Minecraft-aware fleet reconciliation/API hypothesis. Independently deployed servers must remain operable when the manager stops or is removed. Before implementing a new controller, falsify adoption of existing CloudNet/Pterodactyl/Pelican/MCSManager/mc-operator primitives: prefer a thin upstream adapter if it preserves standalone parity, provider-neutral identity, and independently durable worlds. One manager owns a local fleet; future federation is optional and must not create a mandatory global coordinator.

## Desired service topology

```text
Players / qualified clients and bots
             |
       Velocity ingress    (only published player entry)
        | optional VIP     (identity + proxy-side admission)
        |
     private backend networks (no published backend bypass)
        +-- Vanilla Java 26.3+ + narrowly scoped VanillaCord
        |     semantic authority for Two Rivers and vanilla gameplay
        +-- Paper adapter
              separately qualified gameplay/runtime lane
                 |
       independently owned durable world(s)
       ZFS snapshot/clone through the provider; explicit world mount

Optional and separate services:
- COLLAGE fleet manager/API: observe -> plan -> apply -> verify;
  discover, reconcile, adopt, inventory, and manage native Apps
- World controller: policy, candidate lineage, release/promotion,
  migration, rollback, receipts, DLE
- Least-authority world-agent: quiesce/save, stage, snapshot,
  activate, restore, resume, hash (no Docker socket; no policy)
- Bots / canonical Gym / generators: consumers and independent
  integration-test actors, not runtime deployment authorities
- Foundry: Compose/source render, provider values, Apps lifecycle,
  storage attachment, secret injection, health, reconcile
```

A **standalone single backend** installed directly as a supported TrueNAS App is a valid first deployment. It must not require Velocity, VIP, COLLAGE, or a world-agent unless that selected topology explicitly requests them. The **managed multi-server** target exposes only Velocity player ingress and denies direct backend bypass. Paper, direct vanilla, proxied vanilla and any translation modifiers have independent qualification profiles; do not silently upgrade evidence from one to another.

## Authority / state boundaries

| Authority | Owns | Must not own |
| --- | --- | --- |
| Runtime image / configuration assembly | Exact immutable server/proxy/plugin/resource-pack releases and tested compatibility | Site secrets, selected world contents, fleet policy |
| Provider / TrueNAS Foundry | App materialization, Compose/wiring, service lifecycle, storage attach, provider health, site-specific secret injection | World release/promotion, gameplay rules, identity provisioning |
| World controller | World identity, provenance/DLE, versions, safe activation/rollback policies and receipts | Direct container authority or Minecraft gameplay semantics |
| Optional world-agent | Narrow quiesce/save/hash/stage/restore verbs on admitted world assets | Docker socket, orchestration policy, unexplained live mutations |
| Velocity + optional VIP | Player ingress, qualified forwarding, proxy identity and admission | World management or independent account/private-key provisioning |
| Optional COLLAGE | Local-fleet desired state, provider-neutral ownership, discovery/re-adoption/reconciliation | Mandatory server operability, native-world ownership, competing shadow runtime |
| SupraCraft/Two Rivers | Vanilla-authored mechanisms, structures, game/story semantics | TrueNAS or Foundry lifecycle policy |

Immutable assemblies follow `DECLARED -> RESOLVED -> CANDIDATE -> QUALIFIED -> APPROVED -> SELECTED -> MATERIALIZED -> SUPERSEDED`. Site bindings (CPU, RAM, ports, storage paths, secrets and selected world) do not mutate the approved software assembly. Do not float `latest` or silently change software on restart. Retain prior approved assemblies for rollback.

## World storage and lifecycle

- World identity and ownership are **separate from App/container identity**. No world or required state may live solely in an ephemeral container layer. External volume and backup provenance must be explicit.
- First native TrueNAS experiment: App-owned `/data` (ixVolume) plus independently durable writable world dataset mounted to `/data/world`. It is valid to delete the App with App-owned volumes while retaining the independently owned world.
- No foreign App, dataset or existing world can be automatically adopted without verifying explicit provider-neutral ownership metadata and exact namespace. A manager restart must recover from native provider state, not shadow directories.
- Activation requires staged candidate + hash -> quiesce -> snapshot current -> activate -> resume -> observe. On failure, restore snapshot and recheck according to [activation transaction v1](../spec/minecraft-world-activation-transaction-v1.json). Every mutation emits a provenance/rollback receipt; destructive replacement is fail-closed.
- ZFS acceleration is a provider capability, not a Minecraft-core assumption; a second provider must preserve logical world identity and safety semantics even with different storage primitives.

## Portable provider materialization

Use container/Compose as the normalized hosting stack with a thin provider adapter. **Provider-native TrueNAS Apps first**, including unmodified upstream native app deployments when they already meet the contract; other Linux/container/OCI hosts are potential providers, not mandatory dependencies. An OCI VPS with Docker/Swarm/CapRover is historical deployment precedent, *not* current proof of uptime or a required platform. Run standalone servers without COLLAGE; separately qualify manager-created parity and owner-tagged re-adoption.

Runtime controls: immutable image references/digests, least privilege, bounded resources, no published backend bypass or Docker socket in world-agent, externalized world/config/plugins and meaningful protocol-level health. Management and secret endpoints remain private.

## Independent acceptance gates

| Gate | Evidence required |
| --- | --- |
| S0 | Spec/source contract and static Compose tests |
| S1 | **Real** vanilla + VanillaCord boot, direct protocol + world persistence |
| S2 | Real Velocity modern forwarding, optional VIP admission, no backend bypass |
| S3 | Same-world direct-versus-proxied *vanilla* semantic transparency |
| S4 | Paper separately boots/forwards with its own identity and behavior evidence |
| S5 | World-agent quiesce/hash/stage/activate/restore in live disposable storage |
| S6 | Exact Foundry source-render/Compose and storage/materialization candidate |
| S7 | Real disposable nested TrueNAS native App lifecycle (catalog/create/start/redeploy/delete/reinstall, status + level.dat, world-retention, zero residue) |
| S8 | Separate explicitly authorized physical TrueNAS HIL; **not inherited from S7** |

A successful `app.create`, container `RUNNING`, or source render alone is **not** a Minecraft ready signal. Verify the exact Java protocol version, `level.dat`, backend ingress identity and durability after lifecycle transitions. Paper never qualifies vanilla/Two Rivers. Stop on any failed or missing oracle, provenance, world ownership or cleanup gate. Public/free-tier disposable GHA qualification is preferred, with one heavyweight VM per shared lane and no private-minute dependency; no mock-server acceptance.

## Known current boundaries (2026-10-12; status must be re-reconciled before use)

- Current first native disposable target is **TrueNAS 25.04.1 + native community/minecraft catalog 1.15.29 + Paper Java 1.21.11**, with pinned Foundry control and image. This target is a **product/lifecycle proving case**, not the vanilla 26.3 gameplay target.
- Real guest [rep 006](https://github.com/SemperSupra/agent-dispatch/actions/runs/38170800682) proved catalog and immutable image plus a native RUNNING App, but refused `app.config` ownership read-back and cleaned all owned objects; it did **not** prove server status or persistence. Current [rep 007](https://github.com/SemperSupra/agent-dispatch/actions/runs/38184480046) is independently testing sanitized read-back reasons; *no product PASS until exact receipt confirms it*.
- The public hosting-stack [S0 contract](../spec/minecraft-hosting-stack-v1.json) is not a full multi-service runtime acceptance. COLLAGE H1-H9 adoption/federation and physical HIL are still unqualified.
- **Physical/local TrueNAS mutation stays on HOLD** pending explicit admission and end-to-end product evidence. No direct site operations are authorized by this document.

## Operations and change discipline

Keep issue/branch/PR/DLE as the authoritative workflow; pin source and produced artifacts, public/secret partitioning, exact acceptance oracles, and rollback plan in each change. Work from live current heads, preserve causal failure receipts and owner-controlled consent gates. Keep a provider-neutral read-only plan/observation path before physical APPLY. A new service, controller, storage mechanism, panel or protocol extension must demonstrably earn its operational cost.
