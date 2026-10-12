# SupraCraft Minecraft deployment and native Paper T6 — 2026-10-12 handoff

**Authority:** [Minecraft hosting stack #53](https://github.com/SupraCraft/mc-server-images/issues/53), [Foundry product #288](https://github.com/SemperSupra/truenas-app-foundry-private/issues/288), [Agent Dispatch execution #588](https://github.com/SemperSupra/agent-dispatch-private/issues/588), [COLLAGE prior-art #1](https://github.com/SupraCraft/collage-private/issues/1).  
**Status:** first **real disposable** native Minecraft Paper App / TrueNAS 25.04.1 T6 **SUPPORTED**; no physical deployment authorization.  
**Priority at handoff:** close this scoped successful experiment, **do not rerun it unchanged**; move to the next independently unqualified hosting-stack lane.

## 1. Resume from durable authority, not an old chat or stale status

1. Read the accepted [portable deployment model](../deployment-model-v1.md), [hosting-stack contract](../minecraft-hosting-stack-v1.md), [stack spec](../../spec/minecraft-hosting-stack-v1.json) and [world activation transaction](../../spec/minecraft-world-activation-transaction-v1.json).
2. Read the canonical [machine-readable Paper T6 acceptance](../evidence/minecraft-paper-truenas-25.04.1-t6-2026-10-12.json). It is a source-linked projection of **one** exact successful disposable run, not proof for all server families or target versions.
3. Reconcile **live issue/PR/branch/workflow heads** before any new mutation or claims. This file is a dated bootstrap baton, not a replacement for GitHub DLE.

## 2. Exactly accepted real system and immutable evidence

| Attribute | Verified value |
| --- | --- |
| Native target | TrueNAS **25.04.1**, guest on the public/free GHA QEMU/KVM RDTE lane |
| TrueNAS catalog | `community/minecraft`, version **1.15.29** |
| Backend | **Paper Java 1.21.11**, exact Java protocol **774**, literal branded ping contract `Paper 1.21.11` |
| Guest workflow | [run #38200675099](https://github.com/SemperSupra/agent-dispatch/actions/runs/38200675099), **completed/success**, commit `50d6aa75835727997395156d4b44c3ce668b38f4` |
| Guest job | `114653615051`, **success** |
| Guest receipt | artifact `11726177363`, SHA-256 `22fba44f416871585af42c4361b090ee42438c48a589a54e1c02841f5ad00c08` |
| Source-control receipt | artifact `11725850775`, SHA-256 `228fc197093c405e9d66480c26b31582beed9d8226aa19fc4fd069526df3666f` |
| Producer control | `SemperSupra/truenas-app-foundry@2cc7e1fe3772f8c532e933b3d7832e6cf985db4e`, control JSON SHA-256 `89cfb74bed600c7c282b12f7a887b47da890e5373a0123931fcf9b5f50e77f07` |
| Upstream catalog source | `truenas/apps@bb96ef6fd8c2708765012a4a3ca3739370a4f92c` |
| Container identity | `ghcr.io/itzg/minecraft-server:2026.9.2-java21@sha256:edf50d431ddc6f73929368e82f4334a405796874f7b0ae11f1edcbb267d670aa` |
| Status-oracle source | `SupraCraft/mc-server-images@1b2227847d56007cdf8b668c00845326827e5fd5` |
| Capsule manifest SHA-256 | `85a740366843255ff2cee80ee0da3550429c911614b91d27325badf58a9d3152` |

The **real guest** verified native App create/config RUNNING owner identity and image, actual Java status and `level.dat` independently at **first boot, restart, redeploy and reinstall**. World sentinel `62d3bef52a11134f83249f6fd8db0e077efd2c849b7d8b4e9f263182000d3f05` survived native App deletion of App-owned storage and dataset reattachment. Final explicit App and world dataset deletion proved `zero_residue=true` and `SESSION_CLEAN`. Acceptance came from the **product receipt**, not a green CI badge alone.

Prior real failures 004–009 established causal corrections (catalog version drift, optional null seed, native empty host-IP default, unknown readiness and exact Paper status branding). They remain negative historical evidence; **rep 010 supersedes the failed acceptance for exactly this target**. Do not discard historical lessons or copy its product PASS to another target.

## 3. Merge/branch positions at this handoff

- Product `SupraCraft/mc-server-images@main`: `d2dd0766f748b6cba92cb8ebfb2433e076f0e064`; [PR #65](https://github.com/SupraCraft/mc-server-images/pull/65) merged. First deployment-model [PR #62](https://github.com/SupraCraft/mc-server-images/pull/62) and strict Paper status-oracle [PR #61](https://github.com/SupraCraft/mc-server-images/pull/61) merged. This handoff may subsequently move `main`; use **live branch head** instead of assuming the date's SHA remains HEAD.
- Producer `SemperSupra/truenas-app-foundry@main`: `ce058e089ac29ce8b3b7a93449c3955b7fd5945d`; [PR #123](https://github.com/SemperSupra/truenas-app-foundry/pull/123) merged.
- Consumer `SemperSupra/agent-dispatch@experiment/gha-kvm-system-rdte`: `50d6aa75835727997395156d4b44c3ce668b38f4`; [PR #395](https://github.com/SemperSupra/agent-dispatch/pull/395) merged **to experiment, not `main`**. Request currently `tn-25-04-1-t6-minecraft-paper-010-exact-paper-ping-protocol-774`; there is **no reason to issue unchanged #011**. The shared heavyweight run census was idle at last inspection; recheck before any later distinct runtime rep.
- Parent [hosting-stack #53](https://github.com/SupraCraft/mc-server-images/issues/53), [Foundry #288](https://github.com/SemperSupra/truenas-app-foundry-private/issues/288) and [Agent Dispatch #588](https://github.com/SemperSupra/agent-dispatch-private/issues/588) hold full immutable receipts and current product boundaries.

## 4. Still unqualified — do not inherit Paper evidence

| Capability / gate | Handoff |
| --- | --- |
| S1 direct vanilla Java **26.3** + VanillaCord | **OPEN** [PR #55](https://github.com/SupraCraft/mc-server-images/pull/55). Last verified blocker: public VanillaCord **2.9.0 immutable release artifact** cannot be fetched/was HTTP 404; earlier direct-build path required an unavailable GitHub Packages credential. `SupraCraft/VanillaCord` Releases remained empty on latest read-only check. Fix the publisher/consumer artifact identity **at its producer**; do not fabricate a URL, expand private access, or substitute a Paper pass. |
| S2 Velocity/VIP; S3 same-world direct-vs-proxied vanilla transparency | Separate end-to-end evidence required; backend port bypass must be blocked in managed topology. [Hosting stack #53](https://github.com/SupraCraft/mc-server-images/issues/53). |
| S4 Paper proxied backend | Separate Velocity/Paper forwarding qualification; native standalone Paper T6 does not prove proxy path. |
| S5 optional least-authority world-agent | Save/quiesce/hash/stage/activate/restore in live disposable world fixture; no Docker socket or release authority. |
| Full stack S6/S7 | Full Compose/Velocity+VanillaCord/Paper+optional VIP Foundry materialization is **not** qualified by the standalone native App rep. |
| COLLAGE local manager / adoption / manager-loss | H1–H9 remain test hypotheses; prefer existing CloudNet or another thin upstream adapter if it satisfies standalone parity and independent world lifetime. [COLLAGE working plan](https://github.com/SupraCraft/collage-private/blob/main/plan/current-work.yaml). |
| Other TrueNAS versions / production | Require target-specific independent F0–F5/product proof. |
| Physical S8 | **PHYSICAL/LOCAL TRUENAS APPLY HOLD.** Separate explicit HIL authorization, exact target, rollback and privacy/secrets admission needed. |

## 5. Highest-useful next small task for the receiving actor

**Prioritize the S1 vanilla + VanillaCord public artifact boundary** while keeping independent lanes possible. Reconcile [PR #55](https://github.com/SupraCraft/mc-server-images/pull/55), the producer [SupraCraft/VanillaCord](https://github.com/SupraCraft/VanillaCord), the [VanillaCord private compatibility authority](https://github.com/SupraCraft/VanillaCord-private/issues/76), and actual release assets/tags/metadata. The required result is an **immutable, publicly retrievable, provenance-verifiable** VanillaCord release/patch artifact *or* an accurately classified publisher defect with an issue-linked producer correction. Only after that, perform actual disposable vanilla 26.3 boot + restart world persistence and then progress to proxy qualification. No synthetic/mock server as substitute for live product acceptance.

Keep small separate branches/issues/PRs, source-/cheap-CI first, exact runnable evidence and negative tests, serialized public/free heavyweight lane only for a distinct justified live rep, explicit rollback/cleanup, and write results into the existing GitHub DLE issues.

## 6. Stop rules and cold-start prompt

- No local physical TrueNAS access/mutation, no silently widened secrets/permissions, no production deployment based on nested RDTE.
- Do not build a replacement Minecraft panel, shadow-world database, or mandatory COLLAGE manager before prior-art falsification; standalone Apps must still operate without a manager.
- Do not call Paper T6 acceptance proof of vanilla 26.3, Two Rivers semantic fidelity, Velocity/VIP, full fleet, alternate TrueNAS versions or S8.
- Never repeat a same-target expensive T6 run just to reconfirm a proven claim.
- If any authority/head/artefact diverges, **observe and explain**, fail closed and choose the smallest correcting change.

> **Suggested resume prompt:** Resume SupraCraft Minecraft hosting-stack S1 from [mc-server-images#53](https://github.com/SupraCraft/mc-server-images/issues/53) and [PR #55](https://github.com/SupraCraft/mc-server-images/pull/55). Read this handoff and the machine-readable Paper T6 acceptance first. Reconcile exact live VanillaCord release/artifact/public access and all PR/branch heads. Fix the smallest verified producer-consumer boundary, run free public source checks, then independently qualify real vanilla 26.3 + VanillaCord boot and world persistence. Keep Paper T6 PASS scoped, full stack and physical TrueNAS on HOLD, and record issue/PR/DLE evidence; do not request new decisions unless truly needed.
