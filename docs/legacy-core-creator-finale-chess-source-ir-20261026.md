# CORE v1.4 creator-grounded Dr. H, chess and control-program mechanism IR

**Report date:** 26 October 2026. **Status:** SOURCE_ONLY / DRAFT HYPOTHESES / NOT ADMITTED. **Author:** UnlikelyWaffle, CORE v1.4, Minecraft Java 1.8.8, **CC-BY-SA-4.0**. **Owner:** [mc-server-images DLE #34](https://github.com/SupraCraft/mc-server-images/issues/34). Original ZIP pinned SHA256 `61092508c78f5dbe36b03a9d0bdb202c5ddfe71f1aada58d62ae81ae93f5a998`; existing complete source graph pinned SHA256 `5a5c25a31e2bcdec1f2d7d18cc4dedfc87c5a43e53cab4529e5bcdac0452efb5`. The later publicly listed CORE v1.4.1 and author's post-release replies are **not** silently treated as exact preserved-world behavior.

## Outcome: source-grounded instruction recovery, not full gameplay reconstruction

We moved beyond block census and creator-story speculation by implementing a version-sensitive, entire-original-world read-only forensic source pass in [`tools/reconstruct_legacy_core_author_scenes.py`](../tools/reconstruct_legacy_core_author_scenes.py). Every one of the **1,445** original commands is SHA-matched. The source and original graph remain inside the existing pinned ephemeral public/free source-custody workcell. Only an allowlisted aggregate report is exported.

An independent source-free [`tools/compile_legacy_core_creator_mechanism_ir.py`](../tools/compile_legacy_core_creator_mechanism_ir.py) consumes the existing four-channel control source result plus the new author-scene result. It emits a typed, aggregate-only three-entry mechanism IR: **four-channel chat/Redstone controller, Dr. H finale, chess skull/hint**. Each entry has a separate input, state, output, feedback, reset and explicit unknown/authority boundary. **Zero** entries are runtime-proven gameplay primitives.

### Original-world source evidence

| Evidence family | Verified original source count | What this actually supports |
|---|---:|---|
| Author command texts with Dr. H references | **48** | Original story content encoded in command text, *not* necessarily the finale |
| Explicit chess story references | **1** | Author text clue, *not* mechanism |
| Entity presence-test commands | **30** | Possible entity/actor state gates globally |
| Entity-removal commands | **43** | Global actor-removal author instructions |
| Source actions mentioning skull materials | **11** | Skull action references; not a demonstrated chess puzzle |
| Smoke-particle command instructions | **5** | Potential visual hint effects |
| **Armor-stand summons with skull token in authored NBT** | **8 / 8** | Direct original dynamic armor-stand + skull composition; **strong chess-related primitive candidate**, but scene match unproven |
| Those eight summons with no explicit `Count` token anywhere | **8 / 8** | Missing explicit count, consistent with later reported bug; **not proof of the runtime item count or the exact chess pieces** |
| Saved armor stands | **952** | Snapshot state, not the dynamic outcomes of eight authored spawns |
| Saved armor stands with original equipment entries | **952** | Saved equipment representation; no recognized skull-equipped stand recorded by this current decoder |
| Skull block tile entities | **5** | Saved skull block state, not necessarily chess positions |
| Saved signs | **104** | Story/instruction source available under custody |

**Source-directed joins and meaningful negative evidence:** the current permitted exact original authored command→command graph links provide **no complete Dr. H dialogue→presence→kill→skull→final dialogue chain** and **no complete chess textual cue→smoke hint→armor-stand state chain**. Exact matching named entity selector shared by `testfor`/ `kill` was **not found** under the bounded 1.8 source parser; named-selector readback and player/actor binding remain unknown. This is a coverage and causal-qualification conclusion, **not proof those puzzles were absent or broken**.

The independently validated original typed sensor graph did reveal **two accepted sensor→Dr. H-referencing command paths** and **two accepted sensor→entity-removal command paths**. **One distinct sensor is common to both categories**, yielding a genuine **source-static shared input** to an original **Dr. H-referencing summon** and an **entity type-filtered kill** action. That is not a command execution order or proof the removed entity is Dr. H. It is the highest value next original source trace target.

### Three-audience IR contract

All audiences read the same [aggregate typed IR producer](../tools/compile_legacy_core_creator_mechanism_ir.py):

- **Human:** read `label`, `inference_tier`, author-reported purpose, `input/state/output/feedback/reset` and `unverified`; display what source supports, a separate what-creator-said field, and an UNKNOWN status rather than confidence theater.
- **Automation:** `compile_ir(story,control)` rejects wrong source/graph SHA, 1,445-command parity breaks, 90 typed input route regression, spurious four-target claims, incomplete delay histogram, any native-executed/promotion input. Emits deterministic machine-readable JSON, not a world file.
- **Agent:** never treat an IR row as a granted assignment/permission, a successful gameplay trial, an accepted 26.3 recipe, a deployment authorization, or a license to disclose original world positions/commands. All outputs fail-closed on unsupported data.

**Mechanism IR current statuses:**

| Candidate | Input | Source state/action | Feedback | Reset | Admission |
|---|---|---|---|---|---|
| Four-channel chat/Redstone controller | 13 clickable actions / 4 targets | Four saved target sites, 9/9/16/18 repeater-stage chains, three terminal `tellraw` and one entity-selector `tp` | Four immediate `tellraw` candidates, three delayed `tellraw` terminal instructions | Four exact source-authored `air` writers | **SOURCE_TYPED_PROGRAM_SKELETON**, actual activation UNKNOWN |
| Dr. H finale | Two strict routes to Dr. H-referencing commands + two to entity kill; one sensor shared by a **summon** and **type-filtered kill** | Global 30 presence / 43 kill operations; exact full ending chain unresolved | 48 original commands referencing Dr. H, not necessarily dialogue; author-reported final scene | UNKNOWN | **CREATOR_INTENT + PARTIAL EXACT INPUT** |
| Chess | Creator claims hint and piece placement; original typed path to smoke not yet proved | Eight original skull-bearing armor-stand summon commands, 952 saved armor stands | Five smoke-particle commands, one explicit chess textual cue | UNKNOWN | **CREATOR_INTENT + EXACT ACTION COMPOSITION**, complete puzzle not proved |

## Prior art and historical oracle use

The [creator/user evidence dossier](legacy-core-author-player-walkthrough-evidence-20261025.md) identifies historical writer explanations, puzzle defects, final story flow and chess hint/armor-stand presentation. We treat them as **EXTERNAL_AUTHOR_CLAIM** or **PLAYER_REPORTED_FAILURE**, not executable source code and not native v1.4 observation. Original v1.4.1 publication (October 2015) postdates the pinned v1.4 release. Zero-count skull bug is compatible with eight missing explicit `Count` tags in original armor-stand commands, but the original 1.8 parser/historic runtime default and scene-specific use still need independent verification.

## Follow-up first failure: source reference is not automatically dialogue

**F-107-SCENE-LABEL-011**: the first IR represented the two Dr. H-referencing typed source paths as `author_dialogue_paths`. The original-world strict shared-sensor audit instead proved that one companion command is **`summon`** and the sibling operation is **`kill` with an entity-type-filtered selector**. Reclassified IR to `dr_h_referencing_command_paths` and changed its input evidence type to `qualified_typed_sensor_paths_into_dr_h_referencing_commands`. The summoned entity and killed entity are not yet exactly joined; author identity, script order and ending progression are **UNPROVEN**. This eliminates an agent-facing semantic overclaim.

## Verification, first failures and corrective actions

- **F-107-SCENE-NBT-010:** first synthetic source-free run [40323039836](https://github.com/SupraCraft/mc-server-images/actions/runs/40323039836) failed because the synthetic per-chunk NBT test imported the main world decoder module, which requires `nbtlib`; the free synthetic runner intentionally does not install original-source dependencies. Fixed: isolate a pure local NBT scalar adapter and defer `nbtlib` import exclusively to the already pinned source-custody worker. Source-free tests then PASS.
- Synthetic no-world regression and adversarial coverage includes misleading Dr. H/chess text, missing exact links, different named-selector entity references, forged graph endpoint, armor stand with zero-count skull, dynamic `summon ArmorStand` with skull but omitted `Count`, absent smoke sensor input, required historical source pins, incomplete original command coverage, four-channel controller integrity and no semantic promotion.
- [Final source-free public GHA **40324204150**](https://github.com/SupraCraft/mc-server-images/actions/runs/40324204150), exact tested HEAD **a5c8628d9397b816aafbbeb07ee8194551826b2a**: **260/260 PASS**.
- [Final pinned read-only source-only original CORE GHA **40324244403**](https://github.com/SupraCraft/mc-server-images/actions/runs/40324244403), exact tested HEAD **fcde161728663923130f093473889333a650a88a**, job **121576709822**: **COMPLETED/SUCCESS**, complete 1,445 SHA matches, 90 known strict typed sensor routes, original saved-NBT actor evidence, privacy/nonpromotion and three-entry IR passed.
- GitHub-derived **aggregate-only artifact 12649959285**, archive digest **sha256:031f3159ce64286e63b73ba668798aa3cdde6646061f06b2e8b457d191184f34**, expires **2026-11-09 12:40:27 UTC**. No original raw commands, per-actor names, coords, reversible IDs, world source or video transferred.

## Final source-only qualification after Dr. H semantic correction

The amended IR names **Dr. H-referencing command paths**, not `author_dialogue_paths`. The original source-connected shared input was independently found to feed a **`summon` instruction with a Dr. H reference** and a **type-filtered `kill @e[...]` candidate**. The entity type/name itself is not published, and the summon/kill pair is **not** proven to act on one individual, run together, or constitute the final scene. The original full finale sequence and chess hint trigger are still unproven.

**Current verified exact runs:**
- [Free public source-free synthetic **40325212196**](https://github.com/SupraCraft/mc-server-images/actions/runs/40325212196): **263/263 PASS**, exact source-free test HEAD `3a09dca7fdeffcbdcf961af6153b78e6cf2f1a4b`. Retains hard negatives on unsafe author-cue interpretation and forged source links.
- [Free public pinned original read-only **40325243744**](https://github.com/SupraCraft/mc-server-images/actions/runs/40325243744): **COMPLETED/SUCCESS**, executed HEAD `223ca46a10e6ca1c4bf2e17ea34f7fef46004b9c`, job `121580135143`, including SHA parity, NBT source, 90 typed routes, redacted Dr. H shared sensor action, three-entry source IR, no native execution, privacy and no-promotion.
- Source-credited derivative artifact **12649859274**, digest `sha256:6b4ad2d7b7fa06622af8b68156c635f835d4308702e24421ffdec5832af9f00d`, expires **2026-11-09 12:48:14 UTC**. Raw original commands, positions, tile/actor names, inventory, and source are not exported.

**First failures:** `F-107-SCENE-NBT-010` synthetic environment's missing `nbtlib` corrected via dependency-free NBT scalar fixture helper; `F-107-SCENE-LABEL-011` overstatement that a Dr. H reference meant dialogue corrected and regression-gated in the public CI. No original Java native execution or deployment occurred.

## Next source-only discriminating experiments (READY)

1. **Dr. H:** within the same approved source cell, start from the *one exact common sensor* feeding original **summon** and type-filtered **kill**. Compare the summoned source actor category with the removal selector type under original 1.8 syntax; determine whether any exact actor identity/dataflow links the two. Do not infer a dialogue event from the Dr. H reference alone. Do **not** assert kill order, actor identity, finale ending or clock behavior from common root alone. Emit safe aggregate only.
2. **Chess:** inspect original eight skull-bearing armor-stand `summon` argument/NBT structure and original item Count defaults; attempt exact typed input/target joins from the five smoke particle hints to author story and skull actor state (not generic map proximity). Distinguish pinned v1.4 authored NBT, saved world, and later v1.4.1 author bug report.
3. **Global multichannel coverage:** preserve existing 10-channel mechanical/electrical/inventory/magic/environment/actor/traversal/presentation/command/progression denominators and unknowns. Reuse the newly qualified IR and validators; avoid duplicating previous broad scans without a new discriminator.
4. **Future native plan only:** after separately authorized original Java 1.8.8 runtime and physical owner gates, one minimal input/no-input/reset comparison would discriminate these reconstructed hypotheses. Existing PR #108 explicit native attribution write refusal is **not** an admission and may **never** be bypassed through a different workflow, runner or actor.

**Gates:** PR #107 draft/unmerged. PR #108 explicit refused original-native attribution STOPPED. No original Java 1.8.8 execution, #27 gameplay-primitive admission, #35 official 26.3 parity/HIL, merge/release, TrueNAS deployment, source custody widening, private runners/paid cloud or credential changes.
