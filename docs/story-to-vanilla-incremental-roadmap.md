# SupraCraft Story-to-Vanilla Incremental Product Roadmap

Status: planning authority, non-disruptive  
Primary tracker: `SupraCraft/mc-server-images#27`  
Current live integration authority: PR #12  
Primary exact modern target: Minecraft Java 26.3

## 1. Product goal

SupraCraft should accept a higher-level story/game description and instantiate it using only vanilla Minecraft server/client capabilities.

The product is not a universal Minecraft simulator.

The product is a **story compiler and runtime planner**:

```
story intent
  -> story/game semantic IR
  -> capability requirements
  -> versioned capability resolver
  -> vanilla lowering plan
  -> world/datapack/command/block/entity/item artifacts
  -> vanilla server/client execution
  -> observation/verification
```

The same high-level story should survive as more native capabilities are learned. Early implementations may be command-orchestrated; later implementations may lower to more native Redstone, mechanical, social, biological, or production systems without changing story intent.

## 2. Avoid a global Big-Bang domain gate

Do not require every Minecraft domain to be fully modeled before the product is useful.

Replace one global completeness gate with **vertical-slice gates**.

A slice may ship when:
- its required semantic capabilities are qualified enough for that slice;
- unsupported capabilities are explicit;
- the chosen vanilla lowering is known;
- the resulting story is observable and verifiable;
- later capability packs can replace the lowering without changing story intent.

Cross-domain semantics are qualified only where a concrete slice consumes them.

## 3. Stable thin waist: Story/Game IR

Keep the authoring model above Minecraft implementation details.

Initial semantic objects:

- `world`
- `location`
- `named_place`
- `region`
- `scene`
- `actor`
- `role`
- `prop`
- `artifact`
- `item`
- `objective`
- `condition`
- `action`
- `transition`
- `dialogue/message`
- `reward/consequence`
- `timer`
- `choice`
- `observation`

Initial relations:

- actor is-at location;
- actor possesses item;
- condition enables action;
- action changes world/actor/item state;
- observation exposes state/event to a player/agent;
- named place occupies a bounded region and can be discovered;
- named place may expose lifecycle, local modifiers, resources, lore, and observation surfaces;
- objective is satisfied by state transition;
- scene transition occurs after objective/condition.

The IR must express intent, not block layout.

## 4. Capability registry

Every lowering primitive is versioned and evidence-scoped.

Suggested states:

- `discovered`
- `structural_candidate`
- `runtime_supported`
- `accepted`
- `composable`

Each capability records:

- edition/version;
- semantic domain;
- exact Minecraft objects/classes/artifacts;
- runtime contract;
- observation contract;
- implementation modes;
- dependencies;
- hard negatives;
- evidence refs.

Implementation modes:

- `native_mechanic`
- `command_orchestrated`
- `hybrid`

A command-based implementation is a legitimate vanilla backend, but it must not be confused with proof that the corresponding native mechanic has been semantically recovered.

## 5. Prioritization principle

Optimize for:

1. end-to-end playability;
2. reuse across many story types;
3. currently qualified evidence;
4. cheap validation;
5. graceful fallback;
6. incremental replacement by more native Minecraft behavior.

Do not optimize for encyclopedic subsystem completeness.

## 6. Capability-pack sequence

### Slice 0 — Compiler skeleton / empty world contract

Purpose:
- prove story -> IR -> capability resolution -> vanilla artifact -> verification.

Capabilities:
- exact version profile;
- world/location coordinates;
- block/entity/item identity;
- observation receipts;
- deterministic artifact generation;
- failure on unsupported story requirements.

No elaborate gameplay required.

### Slice 1 — Playable quest MVP

Highest priority.

Story example:
- player arrives at a location;
- receives a message/objective;
- obtains or delivers an item;
- world state changes;
- receives acknowledgement/reward;
- scene completes.

Required packs:
- programmable/control;
- basic inventory/items;
- observation plane;
- basic entity/player targeting;
- text/sign/book/title/chat output;
- location/world-state manipulation.

Primary backend:
- vanilla commands/datapack/scoreboard-style orchestration where qualified;
- ordinary vanilla entities/items/blocks for embodied state.

Why first:
- exercises the complete product loop;
- supports many narrative genres;
- does not wait for deep mechanical/AI/ecology semantics.

### Slice 1.5 — Named place / landmark MVP

High-leverage early slice.

Purpose:
- make the world contain discoverable, persistent, named places with local meaning;
- exercise Story IR, world generation, discovery, persistence, observation and local actor modifiers;
- provide a reusable substrate for natural wonders, ruins, temples, monuments, sacred sites, resource sites and hazards.

Story examples:
- discover a named volcano;
- discover a healing spring or sacred grove;
- enter a warding monument that repels hostile mobs;
- find a ruin that exposes lore or a resource;
- discover a place whose state changes over time.

A named place is not a new physics domain. It is a story/world object that composes capability packs.

Minimum IR:

- stable `place_id`;
- display name;
- archetype;
- exact world/dimension/region geometry;
- discovery condition and discovery state;
- lifecycle/state machine;
- local modifier fields / aura;
- resource/depletion/regeneration state;
- visual/audio/observation surfaces;
- lore/artifact hooks;
- persistence/provenance;
- versioned vanilla lowering plan.

Initial archetypes:

1. **Volcanic wonder**
   - dormant -> rumbling -> erupting -> cooling -> resource-rich;
   - periodic or condition-driven eruption;
   - terrain/world-state mutation;
   - after cooling, exposes mineable resource zones;
   - if generated underwater, repeated material accumulation may create emergent land/island geometry once configured thresholds are met.

2. **Healing sanctuary**
   - discoverable named site;
   - bounded radius;
   - players inside receive a configured healing/recovery modifier;
   - observation/lore communicates the effect.

3. **Warding monument**
   - bounded influence region;
   - hostile-mob presence is reduced/repelled through the selected vanilla lowering;
   - exact implementation may initially be command-orchestrated and later replaced by more native mechanics.

4. **Sustenance shrine / fertile site**
   - bounded hunger/saturation, crop, or resource modifier;
   - exact effect is capability-scoped and versioned.

Implementation modes:
- `command_orchestrated` first for discovery, timers, local effect fields and state transitions;
- `native_mechanic` where independently qualified;
- `hybrid` for physical landmark geometry plus programmable state/effects.

26.3 provides a strong vanilla implementation substrate for this slice:
- datapack predicates and command conditions;
- commands that inspect entities/items/state;
- `/place` feature support;
- status effects and client presentation surfaces;
- persistent datapack/storage/scoreboard-style state where used by the selected lowering.

Do not treat a place's aura as a new global domain. Model it as a localized rule/effect attached to the place and qualify only the actor/world interactions consumed by that archetype.

Why early:
- gives exploration immediate narrative value;
- supports procedural discovery without requiring rich NPC AI;
- exercises incremental compilation and verification;
- becomes a reusable anchor for later crafting, ecology, NPC, artifact and quest content.

### Slice 2 — Physical puzzle / machine story

Story example:
- find/activate controls;
- open a path;
- machine changes world geometry;
- success is observable.

Required packs:
- electrical;
- mechanical;
- observation;
- programmable orchestration only where necessary.

Leverages existing strong Redstone and piston evidence.

This is the first slice where native-mechanic lowering should be preferred over command orchestration when qualified.

### Slice 3 — Workshop / production story

Add Transformation/Production domain.

First representative families:
- shaped/shapeless crafting;
- timed cooking/smelting;
- one stateful transformation family such as brewing or enchanting.

Later:
- smithing;
- anvil;
- grindstone;
- stonecutter;
- loom;
- cartography;
- Crafter;
- other station semantics.

Story examples:
- collect ingredients -> craft key/tool;
- process ore -> build machine part;
- brew item needed for next scene.

### Slice 4 — Social NPC / economy story

Add Actor/Social/Economic domain.

Initial targets:
- villager identity/profession;
- bounded trade interaction;
- simple schedule/location behavior;
- wandering trader as separate actor type;
- reputation/trade-state only as evidence permits.

Story examples:
- speak/trade with villager;
- obtain resource through economy;
- NPC availability changes by scene/state.

Avoid attempting full mob AI first.

### Slice 5 — Farming / living-world story

Add Biology/Ecology/Lifecycle.

Initial targets:
- one crop growth/harvest loop;
- one animal breeding/maturation loop;
- one visible variant/color trait.

Then:
- more crops;
- tree growth;
- taming;
- pollination;
- variant inheritance/selection;
- broader husbandry/ecology.

Story example:
- restore farm;
- breed/raise required animal;
- grow ingredient for a later production step.

### Slice 6 — Rich artifacts and media

Add Artifact/Representation plane.

Initial targets:
- written/sign text;
- paintings/variants;
- music disc + jukebox;
- banners/patterns;
- maps/books;
- decorated pots/pottery;
- named/lore-bearing items.

This layer enriches story expression without becoming another physics domain.

Artifact semantics include:
- identity/content;
- representation;
- authorship/provenance;
- visual/audio meaning;
- encoded information.

### Slice 7 — Rich actors, ecology, and systemic stories

Only after earlier slices work.

Potential additions:
- broader mob behavior;
- faction/reputation;
- villages/raids;
- pets;
- utility mobs/golems;
- richer AI interactions;
- multi-stage economic/ecological systems.

This is intentionally later because it can become an unbounded AI/world-simulation problem.

## 7. Domain/plane model

Core semantic domains now become capability packs rather than a universal completion checklist:

1. Electrical
2. Mechanical
3. Programmable/Control
4. Inventory/Transport
5. Transformation/Production
6. Biology/Ecology/Lifecycle
7. Actor/Social/Economic

Orthogonal planes:

- Observation
- Artifact/Representation

Objects can participate in several domains/planes.

Examples:

```
hopper:
  inventory
  + electrical boundary when enabled state is controlled

furnace:
  inventory
  + transformation
  + observation
  + possible electrical interaction

villager:
  actor/social
  + biology lifecycle
  + inventory/economy
  + observation

music disc:
  artifact
  + inventory
  + observation/audio
  + electrical interaction via jukebox/comparator where qualified
```

## 8. Vertical-slice dependency rule

Do not globally wait for all domains.

For each story slice:

```
story feature
  -> required semantic capabilities
  -> required domain contracts
  -> required interaction contracts
  -> available implementation mode
  -> verification contract
```

Only those dependencies gate that slice.

This replaces a global Phase-B fan-in with **local composition gates**.

## 9. Fallback policy

If a native mechanic is not yet qualified:

1. prefer another qualified vanilla mechanic if semantically equivalent for the story intent;
2. otherwise use a command-orchestrated vanilla implementation;
3. otherwise mark the capability unsupported and fail closed.

Never silently approximate story semantics.

Every compiled story should be able to report:

- requested intent;
- selected implementation mode;
- exact vanilla primitives used;
- version;
- known semantic limitations;
- verification evidence.

## 10. Incremental quality ladder

For each story feature:

### Level 0 — Generated
Artifacts/world changes can be produced.

### Level 1 — Playable
A human can complete the intended story loop.

### Level 2 — Deterministically verified
Automated checks confirm expected state transitions.

### Level 3 — Native-semantic
The implementation uses independently qualified native mechanics.

### Level 4 — Portable
The feature passes on more than one exact Minecraft version/profile.

### Level 5 — Alternative lowering
The same story intent can be implemented through multiple qualified vanilla mechanisms.

We should improve features vertically up this ladder rather than waiting for every feature to reach Level 5 before shipping anything.

## 11. Immediate priority order

### P0
Build Story IR + capability registry + resolver skeleton.

### P1
Deliver one end-to-end quest MVP using:
- programmable/control;
- inventory/item state;
- observation;
- simple actor/player references;
- vanilla textual/visual feedback.

### P1.5
Deliver one named-place MVP with:
- discovery;
- stable identity/name;
- persistent state;
- bounded local modifier;
- observation/feedback;
- one dynamic archetype (volcano) and one static-benefit archetype (sanctuary or monument).

### P2
Deliver one physical puzzle using existing electrical/mechanical evidence.

### P3
Introduce Transformation with one crafting and one timed-production primitive.

### P4
Introduce one bounded villager/trade story.

### P5
Introduce one crop and one breeding lifecycle.

### P6
Add one rich artifact/media story path.

This sequence produces a useful product after P1 and increasing native richness thereafter.

## 12. Non-disruption

Existing causal-machinery evidence remains valid.

- Do not discard the four-domain work.
- Electrical/mechanical/programmed/inventory evidence becomes capability-pack evidence.
- Existing Phase-A acceptance-ready state is preserved.
- No new domain becomes a prerequisite for unrelated existing slices.
- New story compiler work starts on isolated branches.
- Existing Redstone promotion spine remains serialized and independent.
- Exact-version evidence remains authoritative.
- Failures and unsupported capabilities remain explicit.

## 13. Revised interpretation of Phase A

Phase A should mean:

**“Enough independently grounded capability packs exist to support the next bounded vertical slice.”**

It should not mean:

**“Every Minecraft subsystem has been completely modeled.”**

Current state already supports the foundation of the first two slices:
- programmable/control baseline;
- basic inventory/hopper evidence;
- strong electrical vocabulary;
- bounded piston mechanics;
- observation-plane model.

Missing for Slice 1:
- minimal Story IR;
- capability registry/resolver;
- basic actor/player/entity identity model;
- story lifecycle/objective state;
- concrete artifact deployment format;
- end-to-end verifier.

Those should be the immediate productization focus.
