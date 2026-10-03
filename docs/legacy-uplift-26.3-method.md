# Legacy-to-26.3+ Uplift Method

Status: executable candidate methodology  
Authority: `SupraCraft/mc-server-images#35`

## Purpose

Recovered worlds are not endpoints. Their useful behavior is evidence for a higher-level contract that may be reimplemented using newer vanilla capabilities.

The uplift pipeline is:

```
legacy artifact
  -> provenance-preserving recovery
  -> behavioral contract
  -> implementation-dependency inventory
  -> target 26.3+ capability match
  -> uplift plan
  -> separate transformed/reimplemented candidate
  -> static validation
  -> exact-version runtime A/B where required
  -> accepted recipe
```

The source artifact remains immutable evidence.

## Rule classes

### SAFE_SYNTACTIC

Use only where an exact source shape maps to an exact modern shape without intended semantic change.

Examples already implemented:
- datapack predicate top-level `condition` -> `type`;
- serialized block-state `Name`/`Properties` -> `id`/`properties`;
- worldgen `configured_carver` -> `carver`;
- worldgen `configured_feature` -> `feature`.

Safe transforms:
- never mutate the input tree;
- write a separate output tree;
- fail on path/key collisions;
- rescan the output;
- fail if automatically applicable safe findings remain.

### STRUCTURAL_REIMPLEMENTATION

Recover the behavioral contract first, then replace an obsolete implementation surface.

Initial patterns:
- command-block chains / one-command machines -> named datapack functions, tags, schedule, storage/scoreboard state;
- legacy item-stack NBT -> explicit data components;
- legacy text components -> current inline component format;
- legacy marker/armor-stand metadata -> modern entity tags/custom data where equivalent.

These require contract-level comparison.

### CANDIDATE_MODERNIZATION

A newer primitive may be cleaner or more expressive, but the old and new mechanisms are not assumed equivalent.

Initial patterns:
- temporary scoreboard arithmetic -> `/compute` / context number providers;
- command-mediated item-on-block transforms -> `minecraft:block_transformer`;
- custom potion/brewing command systems -> data-driven 26.3 brewing recipes;
- visual-only hacks -> `/posteffect`.

These stay advisory until runtime evidence exists.

## Uplift recipe schema

Every accepted recipe should record:

- recipe ID;
- source version/range;
- target exact version/range;
- recovered intent;
- source mechanism signature;
- target mechanism signature;
- rule class;
- automatic/advisory status;
- preconditions;
- exclusions / hard negatives;
- required state migration;
- observable contract;
- timing contract where relevant;
- multiplayer contract where relevant;
- persistence/reload contract;
- static evidence;
- runtime A/B evidence if required;
- rollback/provenance pointer to legacy evidence.

## Behavior-first selection

Do not modernize because a primitive is newer.

Prefer an uplift when it improves one or more of:

1. exact-version support;
2. maintainability;
3. explicit state/provenance;
4. composability with Story/Game IR;
5. observability/testability;
6. performance or failure isolation;
7. ability to express the same intent without implementation leakage.

If none of these are improved, preserving the legacy mechanism behind a version adapter may be better.

## Overlay architecture

The Voidblock 26.2/26.3 intake provides the first concrete pattern:

- orchestration/state logic stays largely stable;
- exact-version worldgen/resource content lives in version overlays.

SupraCraft should generalize that into:

```
story / behavioral contract
        |
stable semantic capability
        |
version adapter / lowering
        |
exact-version datapack/world/resource artifacts
```

Version churn should be absorbed as low in the stack as possible.

## Differential uplift

When both a legacy implementation and a maintainer-provided modern implementation exist:

1. pin both exact sources;
2. recover structural inventories;
3. normalize path/schema changes;
4. compare stable semantic surfaces separately from resource-content additions;
5. derive candidate rules only from repeated, explainable deltas;
6. validate a generated uplift against the maintained modern target where possible;
7. preserve unexplained deltas as UNKNOWN rather than guessing.

## Command-block recovery

Command-block worlds require special care because physical placement can itself be semantic.

Before replacing with functions, recover:

- execution mode: impulse/repeating/chain;
- facing/order;
- conditional flags;
- tick/update cadence;
- comparator/output dependencies;
- Redstone trigger dependencies;
- spatial dependencies;
- block-update dependencies;
- persistent NBT/state;
- visible/audible presentation;
- failure paths.

Only the purely programmable portion may be collapsed into functions automatically after evidence establishes that physical semantics are irrelevant.

## State uplift

Classify legacy state before migration:

- gameplay-authoritative persistent state;
- transient computation state;
- derived/cache state;
- presentation-only state;
- debugging/instrumentation state.

Examples:
- scoreboard objective used as a quest flag: preserve as semantic state or map explicitly to another persistent store;
- scoreboard values used only for intermediate arithmetic: candidate for `/compute`;
- armor-stand marker used only as key/value storage: candidate for custom data/storage;
- armor stand whose location/collision/presence is observed in-world: not a storage-only replacement candidate.

## Validation ladder

### U0 — detected
Legacy pattern found.

### U1 — mechanically transformable
A target representation can be generated.

### U2 — structurally valid
Target parses/loads and references resolve.

### U3 — behavioral equivalent
Bounded observable traces match.

### U4 — exact-version qualified
Target runs on the intended 26.3+ version with hard negatives.

### U5 — generalized recipe
Rule succeeds on more than one independent legacy artifact.

A rule is not a reusable uplift primitive until U5.

## Current executable implementation

- rule catalog:
  `bench/worldgen/corpora/legacy-uplift-rules-26.3-v1.json`
- analyzer/materializer:
  `tools/analyze_legacy_uplift_candidates.py`
- tests:
  `tests/test_legacy_uplift.py`
- CI:
  `.github/workflows/worldgen-legacy-uplift-263.yml`

The implementation currently auto-applies only SAFE_SYNTACTIC rules.

## Next corpus-driven candidates

After Voidblock:

1. Quillmark 26.2/26.3 predicate migration — independent validation of predicate uplift.
2. Mining Drills / one-command machinery — command-block-to-datapack recovery.
3. Parkour maps — checkpoint/timer/cutscene uplift and modern observation primitives.
4. Skyblock progression maps — recipes/resource progression/state migration.
5. legacy CORE 1.8.8 command machinery — stress test for older command semantics.

Each candidate should produce a recipe or a preserved negative result.
