# CORE v1.4: whole-world original command-purpose inference (source-only)

**Purpose and priority correction (2026-10-25).** Before investing in more one-at-a-time native activation or gameplay-primitive reconstruction, review every authored command block and all known sensor→command paths *together* to infer what CORE likely does. This is a SOURCE-STATIC purpose-inference work product, not actual player intent, an original native functional demonstration, an admitted Story/Game IR primitive, or a Minecraft 26.3 uplift claim.

**Authority:** [#34](https://github.com/SupraCraft/mc-server-images/issues/34), draft PR #107. #27 causal/semantic admission and #35 official modern-version uplift remain separate. PR #108's platform-refused native attribution workflow remains STOPPED and must never be retried/rerouted. No native, world save mutation, production, TrueNAS, merge, release or private Actions. Forward storytelling continues independently.

## What was actually inspected

Existing public, $0, disposable pinned SHA-verified **read-only** original workcell reads all original Java 1.8.8 CORE v1.4 command tile entities and the frozen causal graph. It compares **each original authored command** with the graph command SHA-256 and performs a second complete enumeration of directed sensor paths with exact parity to the already-qualified strict ranker. All original strings, position identities, commands and complete graph remain ephemeral in source custody. The public aggregate has counts, coarse standardized inference categories, warnings and creator attribution only; no per-command inventory that could reidentify a source command location or reconstruct command payloads.

Corpus: **CORE v1.4** by **UnlikelyWaffle**, **CC-BY-SA-4.0**, original Java **1.8.8**. Original ZIP SHA256 \`61092508c78f5dbe36b03a9d0bdb202c5ddfe71f1aada58d62ae81ae93f5a998\`; frozen graph SHA256 \`5a5c25a31e2bcdec1f2d7d18cc4dedfc87c5a43e53cab4529e5bcdac0452efb5\`.

The first exact pinned original semantic census [run 40222821760](https://github.com/SupraCraft/mc-server-images/actions/runs/40222821760) SUCCEEDED at source/workflow head \`6634e95e97df6a5aa2e6613567ce325d300c5f2c\`:
- **1,445 / 1,445** original command blocks fingerprint matched (all source-authored command entries examined).
- **90** typed sensor-to-command source-static routes covered, reaching **89** distinct command blocks from **49** source sensors.
- **109** shared exact setblock target groups across the full command corpus (not necessarily 109 gameplay mechanisms): **59** redstone-power-source on/off/reset candidates, **10** place/remove/reset, **36** multi-state reconfiguration, **4** same-class multi-writer unknowns. This is where one-at-a-time uniqueness assumptions were especially misleading.
- Of the 90 named typed paths, authored verb hypotheses: **46** single-block state configuration, **7** region fill, **4** structure clone/copy/reset, **10** relocation, **7** inventory clear/condition, **4** status effects, **3** entity summons, **2** entity removals, **2** weather, **1** spawnpoint/respawn, **1** gamerule, **3** unknown/unclassified. This is command *syntax*, not observed effect or gameplay.
- Among the 46 routed setblock verbs, **17** write Redstone power blocks, **3** write air/removal, and **26** have material *not safely classified* by this initial source-only material allowlist. Do not silently relabel those 26 as known puzzle types.
- **No original native actuation, command evaluation, block delta, graphical player interaction, 26.3 parity or semantic primitive acceptance** took place.

## How to interpret these findings

**High-value inference:** CORE appears to contain extensive block-state controllers and **shared-target multiwriter systems**, including Redstone-power setting/clearing pairs; these could function as puzzle phase controllers, gate open/close, timers, reset circuits, area transformations or coordination. These possible gameplay interpretations are **not mutually exclusive** and do not imply player-accessible input, physical conduction, correct runtime ordering or intent.

**Separate potential output behaviors:** The original code expresses region rewrites/copy/reset, teleportation, inventory changes, entity/spawn/status effects, checkpoints and environment changes. Treat these as candidate behavior *families*, not independent gameplay systems or a proved authored narrative.

**Important scope limit:** 90 strictly routed candidates are a **known subset** of the much larger 1,445-command authoring system. Commands without one of these routes may still fire via other conduits, chains, opaque-solid power, schedulers, command-written power, world updates, or player state. Do not call them inactive. No complete mission/level progression semantics has been reconstructed merely by grouping source verbs. Original nearby signage, room geometry, command-chain/scoreboard state and save-stage annotations would be useful *only if* source-safe contextual inference can actually discriminate a functional group.

## Source-only qualification implementation

- \`tools/infer_legacy_core_gameplay_purposes.py\`: full graph/command census, source SHA-pinned read, strict typed route parity, exact per-tile-entity command fingerprint checks and source-verb/material/target grouping; never emits original text, source ids, commands, positions or fingerprints in derivative.
- \`tests/test_infer_legacy_core_gameplay_purposes.py\`: **12** source-free hard negatives on unsupported facing, reversed edges, source-hash mismatch, ambiguous source, duplicate projections/nodes, shared target state changes, material classification, unknown author verbs, source privacy and nonpromotion.
- Existing public/free source-only workflows updated in place, no new workflow, no PR #108 native workflow change. Initial synthetic job **40222815773** FAILED due to an *optional NBT import in the source-free CI*, not a source/semantic defect. Fixed by isolating pure original command parsing from \`nbtlib\` in commit \`e148fa051e277dd7b397158580e4679062603432\`; later synthetic tests passed. Never present initial failure as an original Java runtime failure.

## Decision and next priority

**Stop assuming every command block is an independent gameplay primitive.** First build source-backed logical *purpose groups* and name the likely behavior, control, reset, output, and missing evidence. The whole-world source scan is the appropriate initial step. Grouping is provisional: stop short of deriving level narratives, precise physical results or reusable capabilities that the source graph cannot support.

**Next READY:** reconcile and inspect the aggregate all-command taxonomy and (when materially useful) source-only *contextual joins* across the 109 shared-target clusters: which have a typed upstream source, scoreboard objective access, complementary setblock materials, source-verified reset phases, or player-facing presentation. Add fail-closed adversarial fixtures, privacy-safe counts and independently review whether any grouping actually improves hypotheses. Read-only and public/free only; no redistributing per-witness addresses or raw command strings. Stop work on source-only context if the result cannot discriminate purpose; request ordinary original-native admission only for a clearly defined and independently reviewed trial, never through the safety-refused PR #108 workflow.

**HOLD:** original Java 1.8.8 native execution, graphical HIL, official 26.3+ port, gameplay semantics promotion, merge/release, private/paid runner and production/TrueNAS remain unadmitted.
