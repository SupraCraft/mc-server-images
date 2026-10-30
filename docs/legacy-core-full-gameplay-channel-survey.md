# CORE 1.8.8 — Whole-world gameplay implementation channel and inferred-purpose survey

**Status:** independent **read-only source-evidence reconnaissance**, not gameplay semantics admission, not an original native Java test, not a modern 26.3 uplift. Follow [DLE #34](https://github.com/SupraCraft/mc-server-images/issues/34). Source **CORE v1.4 by UnlikelyWaffle**, Java **1.8.8**, **CC-BY-SA-4.0**; pinned ZIP SHA256 `61092508c78f5dbe36b03a9d0bdb202c5ddfe71f1aada58d62ae81ae93f5a998`, complete derived graph SHA256 `5a5c25a31e2bcdec1f2d7d18cc4dedfc87c5a43e53cab4529e5bcdac0452efb5`. Original source text/world/commands/inventories/coordinates stay ephemeral in the existing qualified source-custody workcell; only source-credited aggregate counters and nonpromotion status leave. Never infer a missing mechanism from an unsupported extractor family.

## Why a full-world pass was necessary

The prior command-focused static analysis qualified **90 directed sensor→command paths** touching 89 command blocks. The actual pinned CORE world has **1,445 exact original command block instructions**; **1,356** have no qualified route from those previously recovered typed sensors. The same original source has **109 repeated exact setblock point-target groups**, of which **85** have no known qualified typed sensor→command connection. Competing writers and disconnected-looking commands may be intentional state machines, sequencers, toggles, resets, scenery or narrative, not failed gameplay.

This source-only census inspects every available legacy Anvil region section, raw saved block family, tile entity and saved entity across **10,145** original chunks, separately from the canonical frozen graph. It independently checks the original ZIP and graph SHA, restricts all decoding to ephemeral custody, and emits only aggregate evidence. Categories overlap, so summed category counts are **not** unique blocks, connected mechanisms or gameplay primitives.

## Observed breadth across original saved block cells

| Potential gameplay implementation channel | Saved block instances in channel | What must be examined before gameplay qualification |
|---|---:|---|
| **Mechanical / kinetic** | **351** | Pistons, movable structures, doors/trapdoors/gates, transport rails, TNT, dispensers/droppers, slime, triggered paths |
| **Electrical / Redstone** | **5,114** | Button/lever/plate/torch, wires, repeater delay, comparator and detector, Redstone source blocks, powered lamps and sensor/clock topology |
| **Magical / alchemical** | **35** | Brewing, potion/enchantment-bearing items, beacons, portals, spawners, summons, status effects, command-created magic and audiovisual cues |
| **Inventory / equipment / resources** | **1,094** | Chest/container state, hoppers/droppers/dispensers, item provisioning/clearing, furnaces, brewing and trade/resource gates |
| **Actors / spawners** | **30** | Mob spawners, entities, armor-stand actors/props, named entities, equipment and potential AI/summon-based logic |
| **Environment / physics / hazards** | **4,597** | Fire/lava/water, fluid flow, webs, falling blocks, ice, crops, cactus, hazard timing and terrain manipulation |
| **Traversal / navigation** | **4,039** | Doors, bridges, ladders, rails, ice/web/parkour surfaces, portals, boat/minecart paths, teleports and checkpoints |
| **Presentation / visual / audio** | **6,349** | Signs, books, banners, heads, lamps, paintings/item frames, note blocks, particle/sound/title/chat commands |
| **Command orchestration** | **1,445** | Every original command-block string, including state tests, scoreboard updates, entity actions, teleports, region/block mutation and presentation |
| **Multiplayer / progression state** | **2,534** | Scoreboard/objectives, respawn, game rules, command/state transitions, player-specific control and coordination |

**Supplementary source NBT observations:** **1,445** original `Control` command tile entities, **1,083** chest tiles, **104** signs (text redacted), **32** legacy `Music` note-block tiles, **21** spawner tiles, **5** legacy `Cauldron` brewing stands, **44** comparator tiles, **3** droppers, **4** banner tiles, **5** skulls and **3** flowerpots. Inventory snapshot: **69** item stacks, **8** with enchantments/enchantment-book indicators, **2** written-page books. Saved entities: **952** armor stands, **2** item frames; **4** entities have redacted custom-name fields, and **952** have equipment metadata. Presence does not prove interactive behavior. No original author text, entities, items, coordinates or command payloads published.

## First failure and corrective action: legacy source type IDs

**F-107-LEGACY-TILE-006:** Initial complete saved-world scan yielded **1,485 unclassified original tile entities** while the independent command graph proved 1,445 command blocks. This was a classifier representation omission, **not missing content**: Minecraft Java 1.8.8 saved command blocks use `Control`, note blocks `Music`, dispensers `Trap`, brewing stands `Cauldron`, etc., rather than newer namespace strings. The source-only collector was corrected with allowlisted 1.8.8 names (`Control`, `Music`, `Trap`, `Cauldron`, `Airportal`, `Piston`, `DLDetector`, `FlowerPot`) and command-minecart aliases; the independent existing source workcell now requires **exactly 1,445** `Control` tiles, matching the independent command extractor. The known initial 1,485 unknowns are now reclassified; the current run has **no unclassified tiles**. Synthetic hard negatives cover privacy and aliases.

## Semantic reading, before gameplay trials

The separate **whole-original-command source-purpose pass** fingerprint-matches **all 1,445 original commands**, not merely the 90 directional routes, and reveals these important *source-authored intent hypotheses*:

- **511** single-block configurations; **70** region mutations; **26** structural copies/resets. Repeated target mutations suggest possible toggles or reset/sequence logic. **109** repeated exact-target groups: 59 potential power on/off/reset, 10 block place/remove/reset, 36 other multistate configurations, 4 same-class multiwriter unresolved.
- **264** entity spawns; **43** entity removal operations; **20** status-effect commands; **108** player/entity relocations. These can implement actor/arena/hazard, role changes or magic-like mechanics.
- **135** player messages, **30** visual feedback operations and **15** audio feedback commands. These can supply narrative, instruction, quest state and feedback independently of Redstone.
- **31** inventory reset/condition commands; **20** item grants; **18** progression/score operations; **30** entity presence tests; **8** world-state gates; **23** contextual command chains. Those may create multi-stage puzzles or resource gates.
- Non-command paths (mechanical, hazards, inventory, terrain, potion, signs/books, armors/props, spawners and portals) can work without a command-block route. They must not disappear simply because the 90 typed routes omit them.

*These are observations of source syntax and components. They do not establish physical actuation, command success, actual player-facing purpose, timing/reset, relative source proximity, or original/native/26.3 equivalence.*

## Next source-only composition / inference priority, no new native permission

1. Build **coherent mechanism families**, not just isolated witnesses. Associate exact authored state writers/readers, scoreboard references, command chains and qualified sensor routes with physical actuator, inventory, mob/potion, environment and presentation evidence. Every proposed join must name its grounding type (exact target, exact typed edge, source NBT/state, same-chunk proximity-only, or conjecture).
2. Decode original 1.8.8 command arguments *inside custody*: classify `summon` entities and effects, `replaceitem`/inventory and `scoreboard` operations, `execute detect` nested triggers, `setblock` material/data/mode, `fill` and `clone` footprints, reward/reset and objective gates. Distinguish physical/magical/inventory/scripted mixes without exporting content.
3. Review localized signs, books, item frame/armor-stand props, checkpoints and room geometry *inside custody* for player instruction/intent. Publish only aggregate evidence-backed purpose labels and unknowns. Do not call co-presence a working circuit or narrative without independent joins.
4. Emit a source-only **purpose hypothesis catalog** (e.g. gate, bridge, timer, obstacle, puzzle reset, reward, boss/actor, teleporter, magic/status, presentation/quest, unknown), confidence and counterexamples; a unique public row must not become a reversible location or command fingerprint. Preserve the complete census, including unsupported/unknown mechanisms.
5. Only after this source catalog earns its keep, nominate a minimal original 1.8.8 native trial under **separate normal admission**. Keep PR #108's previously safety-refused native attribution workflow an independent hard STOP. Independent #27 semantics and #35 official Java 26.3 graphical/native uplift remain HOLD. Do not merge, release or deploy TrueNAS.

**Proof:** public disposable $0 source-free synthetic [run 40223427250](https://github.com/SupraCraft/mc-server-images/actions/runs/40223427250), **189/189 PASS**, exact synthetic head `c50083a22d7b7b048b4e8722ffa85c0c982ca8fb`. Pinned original, identical graph digest source-only [run 40223459947](https://github.com/SupraCraft/mc-server-images/actions/runs/40223459947), exact workflow head `fc2c99a5153a20f551afab43eb9903cf0508b255`, **COMPLETED/SUCCESS**, derived attributed artifact **12609743890**, GitHub-supplied archive digest `sha256:a84e1e221766aa46b240223b7ef3c0696fda11d0a935b19ba0aaecd76fce8f87`, expires **2026-11-08**. Retention and source-custody guards passed. Sources are static original world, not native gameplay observations.
