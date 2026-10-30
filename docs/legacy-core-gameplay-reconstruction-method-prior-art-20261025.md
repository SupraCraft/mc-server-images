# CORE gameplay reconstruction methodology — multilingual prior-art sweep and architecture

**Research date:** 2026-10-25. **Status:** REVIEWED methodology proposal, NOT an executable implementation or gameplay admission. **Owning DLE:** [mc-server-images #34](https://github.com/SupraCraft/mc-server-images/issues/34). User direction: reconstruct *what whole systems are for* before one-by-one native trials; include mechanical, electrical/Redstone, magical, inventory/resource, entities, environmental, command, audiovisual, navigation and story/progression mechanisms.

**Source baseline:** UnlikelyWaffle CORE v1.4 / Minecraft Java 1.8.8 / CC BY-SA 4.0; original ZIP SHA256 `61092508c78f5dbe36b03a9d0bdb202c5ddfe71f1aada58d62ae81ae93f5a998`, complete causal graph SHA256 `5a5c25a31e2bcdec1f2d7d18cc4dedfc87c5a43e53cab4529e5bcdac0452efb5`. Verified source-only: 10,145 chunks, 1,445/1,445 original command tile texts SHA matched, 90 typed sensor→command routes reaching 89 commands, 109 shared setblock targets, 10 broad implementation channels with evidence; **none are native gameplay claims**. Prior census and DLE: #34 comments 6401746307, 6401773068, 6401798585.

## What is being reconstructed?

A **gameplay mechanism** is a functional subset of original-version world/engine rules that takes player/environment input and an initial state, evaluates conditions, causes a state transition, produces feedback or consequences, and has identifiable persistence/reset/progression behavior. The **gameplay experience** is the higher-level composition: challenge, player affordance, objective, intended sequence, rewards, failure path and narrative. A chest, a named entity, a sign, a piston or a command block by itself is neither a mechanism nor a gameplay experience.

Require a **five-level reconstruction**, explicitly linked but separately admitted:

1. **Original evidence**: world/chunk, tile, entity, inventory, scoreboard and author text (only inside source custody); immutable digest/version, author attribution.
2. **Implementation graph**: electrical typed power, mechanical update/movement, command data/control dependence, selectors/scoreboards, inventory transport, entity events, environment physics, transitions and presentation.
3. **Executable mechanism hypothesis**: guarded transition system or timed Mealy machine with inputs, state, action, state writes, observable output, repeat/reset and adversarial alternatives.
4. **Player-facing gameplay model**: what is playable, accessible, signposted, rewarded, gated or narratively meant; author evidence distinguished from conjecture.
5. **Reusable mechanism IR + acceptance contract**: version-neutral behavior descriptor, original-era transition oracle, assets/provenance and 26.3+ uplift contract. No later stage obtains authority from a mere static label.

## SOURCE-ONLY reconstruction algorithm: Discover → Observe → Plan → Apply → Verify

### A. Preserve original bytes and use the exact historical semantics

Hash and parse the exact 1.8.8 Anvil region sections, block IDs and metadata, legacy TileEntity IDs (`Control`, `Music`, `Cauldron` etc.), entity NBT/inventories, player/global scoreboards, signs/books/heads and any present world metadata. Inventory original world, region, dimension, known source license, available creator documentation and resource packs (absence is a recorded gap). **Never convert the only authority to post-1.13 blockstate or run a modern engine as the original behavior oracle.** Source-custody content, reversible coordinates, raw command text, identity and hashes of individual tiles must not leave the permitted ephemeral read-only cell. Historical original engine semantics for redstone, button support orientation, BUD/quasi-connectivity, sticky piston, hopper, entity, tick order and 1.8 execute selectors should be derived from period-matched authoritative classes/tests, not guessed from modern tutorials.

### B. Build one typed, temporal, multi-domain dependency hypergraph

In custody each node carries exact original position or original state identity, class, version, source proof and possible state; edges have **source/type/evidence**, *not* a generic adjacency relation:

- Redstone: pressed buttons/plates, lever, tripwire, comparator/container output, dust and repeater direction/delay, torch, block-conduction/power, clock, piston and command activation; all contingent on 1.8.8 update semantics.
- Mechanical/traversal: door/trapdoor, pistons and block push/pull, gravity, rail/minecart, slime/bounce, ladder/ice/web, portal and vehicle paths, loaded chunk effects.
- Command/control: parse complete (including nested `execute detect`) original commands as grammar/AST and resolve grounded target footprints/selectors, `setblock/fill/clone`, `testfor/testforblock`, command success, scoreboard/objective reads/writes, entity spawn/kill/teleport/effect, inventory give/clear/replaceitem, `tellraw/title/playsound/particle`.
- Inventory/economy: chest/hopper/dropper/dispenser slots, item counts/data/enchantments, furnace and brewing, comparator fullness, equipment/player inventory, crafting/cost/reward/trading.
- Entity/magic/environment: spawners, bosses/armor stands, AI triggers, potion/effects/enchanting/beacons, fire/lava/water/crops/falling block, daylight/weather/game rules. Magical is a **phenomenological gameplay category**; require actual evidence before interpreting an implementation as a spell.
- Player/story: spawn location, accessible paths, instructional signs/books, map/textures/art/audio, feedback messages, rewards, reset points, spatial puzzle rooms and possible multiplayer player/role constraints. Keep author-stated meaning, visual inference and general game trope guesses separately.

Use **multiple edge types**: `EXACT_DIRECT_TYPED`, `SOURCE_AUTHORED_TARGET`, `EXACT_STATE_READ_WRITE`, `EXPLICIT_AUTHOR_CUE`, `VERSION_ENGINE_SUPPORTED`, `GEOMETRY_PROXIMITY_ONLY`, `RUNTIME_OBSERVED`, `CONJECTURE`, `CONTRADICTORY`. Only first five may build source-supported candidate logic; proximity suggests a search, **not causality**. Do not exclude the 9 previously ambiguous same-target writers from conceptual analysis—paired writes may be deliberate reset/toggle.

### C. Infer boundaries from behavior, not chunks

**Start at outputs and player affordances as well as inputs**, not at the first button: doors/passages/block mutations, portal/teleport exit, chest reward, potion/status, mob trigger, scoreboard/win, message/audio/lighting. Run *backward slicing* of possible state writers and guards, and *forward reachability* from player actions, clock/sensor inputs, inventory/score changes. Add spatial geometry and authored signs inside custody. Condense exact writer/reader strongly-connected subgraphs, infer clock/reset and shared state; preserve distinct mutually-controlling components. Partition into bounded candidate subsystems through cut points (clear interfaces, versioned source edges), not arbitrary chunk or distance boundaries.

**Key rationale:** of 1,445 original command blocks, 1,356 have no *currently qualified named typed sensor* path; among 109 multiwriter targets 85 have no known named typed sensor input. They are neither inert nor proven active. Use command-target dataflow, scoreboards, remote selectors, contraption clocks and indirect mechanisms rather than repeatedly scanning for nearby Redstone.

### D. Learn rules with explicit uncertainty before active gameplay tests

Represent each candidate as `(state, input, guard, actions, output, next_state, timing, reset)`; symbolic/static reasoning computes **possible** transitions, contradictory writers, unreachable states under supported constraints, minimum entry and feedback/reset paths. Compile to an intermediate **Mechanism IR**, not runnable shell or arbitrary command execution. Use evidence-based interpretation ranks, not invented numeric confidence: `AUTHOR_EXPLICIT`, `SOURCE_PROVEN_SYNTAX`, `ENGINE_SUPPORTED_POSSIBLE`, `WEAK_CONTEXTUAL`, `UNKNOWN`, `REFUTED`, `NATIVE_BEHAVIOR_VERIFIED`. Distinguish player intent from observed rule. Contradiction, ambiguity and negative space are first-class objects.

Use AI/LLMs for bounded **hypothesis generation from sanitized aggregate or authorized in-custody context**, always checked by deterministic syntax/graph/property oracles and independently reviewed. Counterfactual reasoner asks *what if the player does nothing, input is pressed twice, inventory missing, reset invoked, two writers race, score changes elsewhere, entity absent, chunks unload?* Without native simulation these are modeled hypotheses, not measurements.

### E. Rank investigation by information gain, not by apparent novelty

For each cluster, prioritize: (i) many downstream states/branches affected, (ii) exact authored endpoints and reset signal, (iii) grounded user-visible affordance, (iv) low cost to falsify, (v) high potential reuse across worlds, (vi) broad alternative hypotheses. Stop generic source scans when they add no typed new relation; record `SOURCE_INPUT_UNRESOLVED` or `AUTHOR_INTENT_UNRESOLVED` and specify the **minimal discriminating observation** required. Keep unresolved orphan commands and non-command paths in coverage denominators.

### F. Test only when admitted, and compare across versions

**Source-only now:** original command AST oracles, typed-edge graph invariants, static guarded reachability, material/state symmetry, reset structure, multiworld known labeled fixture calibration, cross-language terminology and source-custody adversarial fixtures. Approved free/public source-custody runner only. No original native execution presumed permitted.

**Only after independent authorization:** disposable original **official Java 1.8.8** copy with reproducible world snapshot, player action sequence (bot/human), per-tick state deltas, negative/sham/perturbed controls, reset/repeat, multiuser and failure states, independent observers (server state + stock-client view). *A partial simulated network-player result or surrogate simulator is not official original native proof.* Then independently construct or uplift version-neutral IR into official **26.3+** test world with before/after semantic equivalence; keep native original, surrogate, and modern tests separately tagged. #108 explicitly safety-refused original native attribution workflow remains STOPPED; no alternate route/workflow/actor/credentials may circumvent. Review, deployment, merge and production stay separate.

### G. Evidence, reuse, and three-audience UX/DX

Emit an **aggregate public catalog** with author credit, coarse mechanism type counts, coverage, uncertainties, unresolved branches, contradiction families and command/asset source digests at the corpus level. Keep private ephemeral exact per-mechanism graphs/command text solely in the approved source cell, deterministically reconstructable from pinned inputs. Public derivative must not expose original source tile identities, positions, raw code, local hashes or reversible witness records; protect against leakage via unique signatures or visual thumbnails. DLE records latest specific commits, authoritative evidence, first failure, corrective action, source pin, decision, coverage, blockers and next approved assignment.

- **Human:** plain-language “what it appears to do / evidence / alternative explanations / what remains unknown,” interactive visual graph via derived-only diagrams, original-room context *only when authorized*, and when/how it could be played.
- **Automation:** read-only `inventory`, `infer`, `explain`, `diff`, `verify`, `export` commands using machine-readable IR/schema, explicit errors and sealed custody boundary; use Go for any new orchestration/API if justified, reuse qualified existing Python analytical tools instead of gratuitous rewrites.
- **Agent:** bounded assignment/target/admission/authority, deterministic oracle outputs, provenance, no self-certification of native success, DLE replay contract, typed unknowns, policy-enforced no-promotion.

## Prior-art sweep (global/multilingual)

Scanned English, Chinese, Japanese, Russian, German, French, Spanish and Thai queries. Sources below represent independently relevant retrieved material; the latter three languages chiefly exposed docs/basic usage rather than a verified end-to-end gameplay reconstruction framework. **Absence of a discovered end-to-end tool is not proof no such tool exists.** We have not audited all source implementations or licensed them for copying.

| Source/language | What it actually offers | Adopt / evaluate / avoid |
|---|---|---|
| [Computational Redstone](https://github.com/Rektoooooo/computational-redstone) (EN, community) | Direct world reading, build harvesting, sign-guided labels, input-output portmap, containers, layer plates, self-reported 195 component library/19 worlds; reports weak structural-only labels, 97.6% per-block steady-state agreement in own test and limited native verification | **Top candidate to evaluate** for segmentation, portmap, sign-as-author oracle, visual proof and source-only library patterns; **not** a 1.8.8 full gameplay engine (1.18.2, pistons/hoppers omitted). GitHub public metadata shows **no declared license**, so do **not copy its source** without clarified permission |
| [MCEdit](https://www.mcedit.net/tools.html) (EN) | Explicit Java 1.7–1.11 historic world inspection, scripting and legacy schematics | Evaluate read-only inspection/visual sanity; legacy/unmaintained, no automatic gameplay semantics |
| [NBTExplorer](https://minecraft.wiki/w/Tutorial%3APrograms_and_editors/NBTExplorer), [Minecraft NBT documentation](https://minecraft.wiki/w/NBT) (EN) | Original world tile, player, entity, inventory and score data | **Adopt grammar/schema lessons** and independently compare historic NBT decode; no causal rule inference |
| [Amulet](https://www.amuletmc.com/readme) (EN) | Modern world converter/editor; home page and readme differ on historical support | **Not original 1.8.8 authority**: its published disclaimer says Java 1.12+, incomplete entity translation; don't use silent conversion to adjudicate 1.8 mechanics |
| [MC-ticker](https://github.com/Breina/MC-ticker) (EN) | Legacy simulator controls Minecraft jar by reflection, tick stepping and rewind; author claims close-to-original Redstone | Architecture opportunity for exact-engine-backed test oracle *if separately admitted*, not substitute for authorization; GitHub public metadata no license |
| [MCHPRS](https://github.com/MCHPR/MCHPRS) (EN) | Fast Redstone server/Redpiler compiler, Minecraft 1.20.4, many non-Redstone vanilla features deliberately absent | Inspiration for graph compilation/speed; **reject** as 1.8 or full-adventure native correctness oracle |
| [PERSHING paper](https://sigtbd.csail.mit.edu/pubs/2016/paper4.pdf), [Redstone Compiler](https://github.com/Redstone-Compiler/redstone-compiler) (EN, MIT) | Electrical netlists → Minecraft layout, clock/delay, circuit abstractions and compiler stages | **Invert the conceptual chain**: source world → circuit topology → typed netlist/logic candidate; original algorithms are **forward synthesis**, not complete reverse recovery |
| [Dislink tools](https://dislink.github.io/) (ZH) | Web-native 3D Java/Bedrock structure viewer, old-format supports, command extraction from structures, visual edits | Evaluate interface ideas and parsing against fixed original fixtures; do not upload original corpus into third-party site, do not treat Bedrock `execute` conversion as Java 1.8 oracle |
| [Microsoft Chinese command-chain guide](https://learn.microsoft.com/zh-cn/minecraft/creator/documents/commandblocks) (ZH) | Worked game-loop / command execution / reward pattern | Useful gameplay design archetypes; guide is **Bedrock**, and describes modern command-chain rules, not native 1.8.8 |
| [German RedstoneWorld analysis](https://redstoneworld.de/worldedit/analyse/) (DE) | WorldEdit region/chunk info, NBT info, block distribution and selected-schematic views | Compare operator-facing diagnostic commands and aggregate block inventories, not proof of functions |
| [Japanese Minecraft engineering codebook](https://zenn.dev/comsan/articles/redstone-research-process) (JA) | Research on 12 redstone development video cases / 97 segments / 131 events; distinguishes layout, test, failure, diagnostics, correction and configuration | **Adopt failure/repair/author-workflow as counterevidence**: a final saved build may contain incomplete or faulty circuits; capture maker workflow only with provenance |
| [Russian redstone logic build](https://github.com/fedor655/minecraft-redstone-logic-build-ai) (RU) | Generates command-based circuitry, independently simulates prior to original-world assembly; inspect saved `level.dat` | Reuse independent simulation/diff principles; **not reverse recovery**, so benchmark only |
| [Deriving Quests from Open World Mechanics (2017)](https://arxiv.org/abs/1705.00341) | Formal logical Minecraft mechanics → dependency ordering, cycles, bottlenecks and emergent quest graph | **Adopt** reachability/goal dependency and affordance-before-“mechanism” separation |
| [Gameplay Trace → Causal Model (2026)](https://arxiv.org/abs/2602.00190) | Contrasts direct LLM-generated rules with two-stage inferred structural causal models and VGDL; reported comparative improvement | **Adopt** explicit intermediate causal model before prose or implementation; benchmark context differs from actual 1.8 world |
| [Multiverse Mechanica (ICLR 2026)](https://proceedings.iclr.cc/paper_files/paper/2026/hash/f9bc7653cf176075e88203d1e83e8c65-Abstract-Conference.html) | Ground-truth causal graph and counterfactual mechanic-learning testbed | **Adopt** controlled counterfactual oracle and negative tests (e.g. input absent, simultaneous triggers) |
| [AALpy](https://des-lab.github.io/AALpy/), [LearnLib/process mining](https://doi.org/10.1016/J.IS.2023.102180) (EN) | Active/passive finite-state/Mealy learning from input/output and event traces | **Future authorized stage only**; original saved files alone do not provide valid runtime membership/equivalence oracles |
| [TAG: Timed automata from logs](https://ojs.aaai.org/index.php/AAAI/article/view/20311) | Timed model inference from runtime event logs | Evaluate timing/reset of authorized original native sessions; can't assert timing from single saved snapshot |
| [Retro-game archaeology: Jet Set Willy](https://intarch.ac.uk/journal/issue45/2/index.html), [Entombed](https://programming-journal.org/2019/3/4/) | Physical+digital evidence, experimental reconstruction, archival history, code/data and independent verification | **Adopt** provenance, historic release context and possibility of original author bugs |
| [Community game-mechanics analysis](https://www.reddit.com/r/gamedev/comments/18b87aa) | State/condition tables → reimplement behavior; advice is practitioner experience, not formal proof | Reinforces recording complete cases and falsifiers before rebuilding |

## Red-team/blue-team risk ledger

| Threat or failure | Preventive corrective action |
|---|---|
| **Confusing 10 channels or 1,445 commands with working gameplay** | Keep distinct denominators: source components, source graph edges, coherent systems, native-verified behaviors, reusable primitives and experienced game loops |
| **Generic adjacency and same-chunk false causality** | Require typed port/data/target/selector exact joins; proximity can only queue a hypothesis |
| **Misleading sign/story clue** | Mark as explicit *author-intent evidence*, not guaranteed actual function; contradictory native controls remain decisive |
| **Unseen original clock/scoreboard/entity trigger** | Bidirectional slicing from outputs, complete author-command graph, unknown-root coverage rather than “inactive” |
| **Historical block IDs, tile names and version logic** | 1.8.8 parser and matched source-era rules, trace invalid modern assumptions; synthetic negative coverage |
| **Update order, BUD/quasi-connectivity and multipart moving blocks** | Model distinct `signal state`, `neighbor update`, scheduled tick, physical actuation and persistence; never call a static wire connection native activation |
| **Static snapshots resemble valid initial states** | Separate save-time snapshot from intended start/reset; multiple saved worlds/backups or authorized reset events needed |
| **Timing, race, multiplayer, transient inventory/entity state** | Symbolic “unknown”, guarded race alternatives and later instrumented per-tick/participant traces |
| **LLM hallucination or confident but wrong purpose** | Explicit evidence tiers, deterministic red-team counterexamples, reviewer disagreement and no semantically promoting weak ideas |
| **Non-original source paths, unsafe third-party tools or unlicensed code** | Digest-and-license pins, no raw source upload, no copying unlicensed tool code, no arbitrary network/credential widening |
| **A refused native attribution path accidentally rerouted** | Explicit #108 safety STOP; native work requires a new independent admission, never a renaming or alternative-runner bypass |
| **Public outputs leak original world locations/commands via uniqueness** | Aggregate-only output privacy gate, no reversible per-system fingerprint or unsanitized visual, nonpromotion guard |

## Experiment and adoption plan, $0 and gated

- **R0 — Baseline integrity & leakage fixtures:** synthetic 1.8.8 structure, mechanical and inventory/magic fixtures; author aliases; no-world test CI; independent source-custody output/privacy oracles. **READY source-only**.
- **R1 — Prior art qualification:** metadata/license audit; run tool *behavior* on synthetic fixtures only, compare precision/recall/false edges and per-tick claims with our independent graph; especially Computational Redstone segmentation and Redstone Compiler netlist philosophy. **READY source-only; do not ingest entire upstream into original custody**.
- **R2 — Full typed graph and bidirectional slices:** phase-separated input sensors, world/score/inventory writers/readers, entity/command/feedback outputs, reachable reset paths; track 109 shared-point writers and previously unknown 1,356 command roots; fail closed if no exact join. **READY source-only**.
- **R3 — Multichannel semantic clustering:** produce IR archetypes, unknowns and source-evidenced counterexamples with coverage; perform privacy-independent review and stop scanning if no new explanatory power. **READY source-only**.
- **R4 — Targeted experiment design:** minimize observations needed to distinguish competing hypotheses (e.g., noop vs button vs reset vs two writers). Publish only plan and coverage; do **not run original native**. **READY to plan, execution GATED**.
- **R5 — Original native, later 26.3+ uplift and Gym:** independently authorized server/client, repeatable trace/differential experiment, then original-versus-modern gameplay property equivalence. **NOT ADMITTED by this research**.
- **O&M**: every source or inferred-mechanism schema change runs free/public synthetic safety and functional fixtures; DLE artifacts carry commits/runs, source custody hashes, source attribution, first failures, owners, targets and next handoff; do not auto-merge, release or deploy.

**Decision:** The earlier single-button-attribution selection becomes a narrow *future falsification* tool; current priority is **whole-system, multi-domain, historical-source-first logic reconstruction**. Prefer adopting principles and qualified standard components over reinventing them; do not equate modern simulators with original Java gameplay, and do not claim user-facing purpose from source statistics alone.
