# Cross-Domain Causal Machinery — Implementation & Deployment Plan

Status: proposed, non-disruptive planning authority  
Public execution authority: `SupraCraft/mc-server-images#11`  
Current integration baseline: `766f5ec4f1b1f2e8c2350a653fbfd68f598ef884`  
Live Agent Dispatch trusted-host boundary: WAIT while `SemperSupra/agent-dispatch-private#381` remains deferred

## 1. Intent

Extend the existing Redstone causal-microscope / EDA effort into a typed, cross-domain Minecraft causal-machinery system without disrupting the already-qualified electrical vocabulary or its promotion spine.

The first semantic pass is deliberately partitioned into **four core domains**:

1. electrical / Redstone;
2. mechanical / geometry-changing;
3. programmable / command/control;
4. inventory / transport / material-flow.

These are the first-look boundaries. Each domain is recovered and qualified independently before cross-domain interaction semantics are introduced.

Presentation/feedback is **not** a fifth peer domain in v1. Lamps, note blocks, text/sound/particle output, and similar surfaces are treated as observable sinks/state surfaces owned by the domain that drives them unless and until evidence shows a distinct reusable semantic model is required.

The system must remain evidence-driven. A mechanism name is a hypothesis until its structural, exact-version runtime, observer-effect, and correlation contracts pass.

## 2. Scope boundary

Initial semantic authority is **Minecraft Java Edition only**, scoped per exact version. Bedrock and other editions are comparison/discovery surfaces only until separately qualified; no Java behavior may be projected onto them by analogy.

## 3. Non-goals

Do not build:

- a universal Minecraft physics simulator;
- a monolithic ontology containing every block behavior;
- one universal equivalence hash;
- one workflow that executes every domain on every commit;
- an alternate scheduler, queue, task database, or retry service;
- a replacement for the vanilla runtime as semantic authority.

Do not weaken existing qualified Redstone contracts to admit broader layouts.

## 4. Architectural decision

Use a **thin shared causal kernel with rich domain adapters**.

### Shared kernel

The common layer owns only concepts needed across at least two domains:

- stable entity/event identity;
- world position or region;
- edition and exact Minecraft version;
- block/entity state snapshot reference;
- typed domain;
- typed port / edge;
- event time and causal order;
- provenance and evidence reference;
- confidence / UNKNOWN state;
- before/after graph or world-state revision reference.

Candidate event time:

`(game_tick, microstep_or_order)`

The second coordinate is optional until exact source/runtime evidence can establish an ordering relation. Same-tick events must never be silently treated as unordered when evidence shows otherwise.

### Domain projections

A world may project into multiple views:

1. **Electrical**
   - dust nets;
   - direct/weak power;
   - repeaters/diodes;
   - comparators;
   - torches;
   - observers;
   - signal strength;
   - electrical delay and feedback.

2. **Mechanical**
   - pistons/sticky pistons;
   - moving-block sets;
   - slime/honey coupling;
   - movable/immovable boundaries;
   - doors/trapdoors/gates;
   - motion choreography;
   - terminal geometry.

3. **Inventory / transport**
   - hoppers;
   - droppers/dispensers;
   - inventories;
   - item transfer;
   - sorter state.

4. **Programmable / command**
   - impulse/repeating/chain blocks;
   - facing/chain continuation;
   - conditional execution;
   - trigger state;
   - exact command identity;
   - success/result state where recoverable;
   - resulting world mutation.

Each of the four adapters owns its native semantics. Shared-kernel edges link projections without forcing them into one algebra.

### Observation / feedback surfaces

Presentation is cross-cutting evidence, not a peer semantic domain in v1.

Examples:
- lamp lit/unlit state;
- note-block output;
- particles, sounds, titles and text;
- other human-visible/audible terminal state.

A surface remains attached to the domain that causes/owns the state transition. If another mechanism consumes that state, the relationship is represented later as an observation/interface edge; this does not create a fifth domain.

## 5. Cross-domain transducers

Treat subsystem boundaries as explicit qualified interfaces.

Interaction work is **Phase B**. It begins only after the four Phase-A domain baselines are independently qualified.

Initial interface families:

- electrical power -> piston actuation;
- electrical power -> command trigger;
- command execution -> world mutation;
- inventory state -> comparator/electrical output;
- piston movement -> neighborhood/block-state change;
- domain-owned observable state -> downstream observer/event, when non-terminal.

A lamp or other feedback surface may be pruned only when terminal in the bounded mechanism. If another subsystem consumes its state, it remains causal, but it remains an observation/interface concern rather than a fifth semantic domain.

## 6. Dynamic topology

Mechanical movement and command execution can alter connectivity.

Represent this as event-sourced graph/world transitions:

`(G_t, event, evidence) -> G_t+1`

Required properties:

- retain pre-state and post-state references;
- identify the exact event or command responsible;
- preserve version/edition provenance;
- permit replay of bounded transitions;
- distinguish observed mutation from inferred mutation;
- never overwrite failure or intermediate states.

The first implementation should support bounded local transitions, not whole-world exhaustive rewrite analysis.

## 7. Evidence hierarchy

For every mechanism:

`exact world -> domain projection -> structural candidate -> runtime contract -> causal correlation -> qualified semantic operation`

Structure alone is never semantic authority.

Behavioral equality is contract-specific. Preserve separate relations for:

- Boolean equivalence;
- temporal equivalence;
- state equivalence;
- strength/analog equivalence;
- mechanical terminal-geometry equivalence;
- inventory-transfer equivalence;
- command-effect equivalence;
- observable-output equivalence.

No single equality relation is authoritative across all domains.

## 8. Workstream decomposition

### S0 — serialized integration / promotion spine

This is the only serialized semantic authority path.

For each promoted family:

1. candidate definition;
2. structural positive and hard negatives;
3. exact-version runtime contract;
4. stock/instrumented A/B where instrumentation exists;
5. zero dropped causal events;
6. static/runtime correlation;
7. durable acceptance baton;
8. catalog + regression promotion in one bounded batch;
9. full clean promoted-head matrix.

Never run two shared-catalog promotions concurrently.

### K1 — thin causal kernel

Goal:
- additive schema for common event/provenance fields;
- typed domain and edge vocabulary;
- optional microstep/order field;
- before/after revision references.

Rules:
- additive only;
- existing Redstone schema remains valid;
- no domain-specific semantics in the shared kernel;
- no migration required for existing accepted artifacts.

### E1 — electrical / Redstone continuation

Continue current qualified vocabulary and source/runtime primitive recovery.

No redesign of accepted electrical netlist representation is authorized by this plan.

### M1 — mechanical primitive semantics

Bounded primitive contracts:

- piston/sticky-piston activation;
- push/pull eligibility;
- push limit;
- slime/honey coupling;
- movable/immovable classes;
- update ordering;
- door/trapdoor/fence-gate state changes.

### M2 — mechanical topology / motifs

Candidate families:

- piston sequence;
- piston door;
- platform/elevator;
- mechanical clock;
- flying-machine-like bounded assembly.

Structural exploration may run before all M1 contracts finish, but promotion requires the exact primitive subset consumed.

### C1 — command primitive semantics

Recover:

- impulse/repeating/chain modes;
- facing and chain continuation;
- conditional execution;
- trigger relation;
- tick scheduling;
- exact dispatch identity;
- command success/result where observable;
- command-caused mutations.

### C2 — command topology

Candidate families:

- command actuation chain;
- command state machine;
- mixed Redstone/command feedback;
- command-driven topology mutation.

### I1 — inventory / transport

Activate when comparator/hopper work becomes READY.

Initial primitives:

- hopper transfer;
- inventory occupancy/state;
- dropper/dispenser actuation;
- comparator inventory signal.

### O1 — observation / feedback surfaces

Cross-cutting, non-peer surface work:

- lamp state transition as electrical-owned observable state;
- note-block/output feedback;
- distinction between terminal display and causally observed state.

O1 does not define a fifth semantic domain.

### X1 — cross-domain transducers

Phase-B interaction work.

Do not begin X1 implementation until the four Phase-A baselines — E1, M1, C1 and I1 — have each established their bounded primitive/state model for the current exact-version campaign.

After that gate, qualify one interface at a time.

No compound mechanism may promote by assuming an unqualified transducer.

### R1 — representative-world mining

Parallel real-world falsifier:

- CORE v1.4 native 1.8.8 projection/census first;
- Savanna Scramble after native 1.19.x causal extractor qualification;
- later published/community worlds where provenance permits.

Classify:

- exact qualified matches;
- routing/layout variants;
- near misses;
- recurring unknown motifs;
- mixed-domain mechanisms;
- version-specific behavior.

### Q1 — metamorphic / equivalence falsification

Mutation families:

- same-net dust extension;
- dead-end branch;
- signal-strength exhaustion;
- repeater insertion/removal;
- fanout addition;
- legal/illegal yaw transforms;
- support-block/conduction changes;
- alternate Boolean decomposition;
- mechanical geometry-preserving and geometry-changing mutations;
- command-chain reorder/conditional mutations.

Each mutation records which equivalence relations remain true.

### L1 — multilingual external corpus

Harvest candidate designs and terminology from English and non-English sources.

Preserve:

- language;
- source/provenance;
- publication date/version;
- edition;
- licensing/redistribution state;
- claimed behavior;
- known caveats.

External labels are hypotheses, not authority.

## 9. Dependency DAG

```
                         +--> L1 external corpus -----------+
                         |                                  |
qualified baseline ------+--> R1 representative worlds ----+--> candidate abstraction evidence
                         |                                  |
                         +--> Q1 metamorphic falsification -+
                         |
                         +--> K1 thin kernel ----------------------------+
                                                                        |
official runtime/source --> E1 electrical primitives ----+
                        --> M1 mechanical primitives -----+--> Phase-A four-domain gate --> X1 transducers
                        --> C1 programmable primitives ---+
                        --> I1 inventory primitives ------+

M1 -> M2 mechanical motifs -------------------------------+
C1 -> C2 command motifs ----------------------------------+--> S0 promotion spine
I1 -> inventory motifs -----------------------------------+
X1 + domain motifs -> cross-domain mechanisms ------------+
```

K1 is additive infrastructure, not a prerequisite for ongoing E1 work. Existing lanes may continue using existing artifacts until they voluntarily emit the new common envelope.

## 10. Non-disruption plan

This plan must not interrupt ongoing qualified work.

### N1. Branch isolation

- current integration branch remains authoritative;
- new domain work uses independent branches/issues;
- no speculative branch may directly edit the shared catalog while another promotion is active;
- reconciliation is one bounded tranche at a time;
- at reconciliation, the **current integration head wins** over stale branch assumptions;
- stale child work must replay/rebase its deterministic tests against the current head before integration.

### N2. Additive schemas

- K1 adds fields/contracts; it does not rewrite accepted Redstone receipts;
- old receipts remain valid;
- adapters may dual-emit old + new envelopes during qualification.

### N3. Shadow deployment first

New extractors run in shadow mode against existing fixtures/worlds:

- no promotion;
- no existing test replacement;
- compare outputs with accepted artifacts;
- preserve mismatch receipts;
- shadow outputs do **not** feed existing metrics, decisions, or promotion gates until independently accepted.

### N4. Feature-gated workflows

Domain-specific jobs should be separate workflow jobs/files or opt-in matrices.

Do not add piston/command/inventory cost to every Redstone commit.

### N4a. Bounded WIP

To prevent parallelism from becoming coordination overhead:

- at most **five code-bearing discovery/primitive lanes** are active concurrently, excluding S0;
- research/corpus lanes that do not mutate shared code do not consume this cap;
- only **one shared-kernel writer** and **one shared catalog/promotion writer** may be active at a time;
- opening a sixth code-bearing lane requires closing, pausing, or explicitly superseding another lane.

This is a WIP policy, not a scheduler or approval service.

### N5. Staged validation funnel

Discovery candidates:

`static/unit -> single-version falsification -> second-version -> instrumented A/B -> full promotion matrix`

The full 20-workflow matrix remains a promotion/integration gate, not a discovery loop.

### N6. Rollback

Every cross-domain integration tranche must be revertible without invalidating earlier accepted Redstone artifacts.

No destructive schema migration until a separately reviewed migration plan exists.

## 11. Implementation stages

### D0 — planning and boundaries

- land this plan after review;
- retain #381 WAIT;
- create independent issues/branches per active lane;
- define qualification receipt fields.

Acceptance:
- no runtime behavior changes;
- no workflow expansion on existing commits;
- current 20-workflow matrix remains green.

### D1 — kernel contract

Implement additive `causal-kernel-v1` envelope:

- identity;
- domain;
- typed edge;
- exact version/edition;
- event time/order;
- provenance;
- confidence;
- state revision refs.

Acceptance:
- existing Redstone artifacts validate unchanged;
- a small synthetic multi-domain fixture can be represented;
- UNKNOWN can be represented without invented semantics.

### D2 — four independent domain baselines

Run in parallel, with no cross-domain semantic dependency:

- E1 electrical/Redstone baseline continuation;
- M1 mechanical piston/sticky-piston bounded primitives;
- C1 programmable/command bounded primitives;
- I1 inventory/transport bounded primitives.

O1 observation/feedback work may record domain-owned output states, but it does not define cross-domain semantics.

Acceptance is domain-specific and exact-version scoped.

### D3 — first transducers, only after Phase-A gate

The gate opens only when E1, M1, C1 and I1 each have a bounded accepted baseline for the exact-version campaign.

Then qualify:

- Redstone -> piston;
- Redstone -> command;
- inventory -> comparator/electrical;
- mechanical/world-state -> observer/event where applicable.

Acceptance:
- exact endpoint state transitions;
- causal ordering;
- no unsupported inferred edge.

### D4 — first cross-domain motifs

Candidates:

- piston door or bounded piston sequence;
- command actuation chain;
- observer/presentation feedback loop only if required primitives are qualified.

### D5 — dynamic topology

Add event-sourced local mutation receipts for:

- piston move;
- command setblock/fill-like bounded mutation.

Acceptance:
- pre/post graph is reconstructible;
- mutation cause is explicit;
- replay agrees with vanilla result for bounded fixture.

### D6 — representative-world cross-domain census

- CORE first;
- Savanna after 1.19 extractor.

Use findings to falsify/extend adapters; do not mass-promote motifs.

### D7 — equivalence and round-trip research

Introduce candidate semantic signatures only after R1/Q1 evidence.

Longer-term:

`world -> recovered semantics -> regenerated candidate -> vanilla runtime comparison`

This is research/qualification, not an initial deployment dependency.

## 12. Deployment topology

### Public/free execution

All executable qualification stays on standard public GitHub-hosted runners.

Hard rules:

- USD 0;
- no private Actions dependency;
- no paid/larger runner fallback;
- bounded timeouts;
- no auto-retry loops;
- no secrets in untrusted PR execution.

### Repository topology

Reuse `mc-server-images`.

Proposed additive layout:

```
bench/worldgen/causal/
  kernel/
  electrical/
  mechanical/
  command/
  inventory/
  observation/
  transducers/
  corpora/
  equivalence/
tools/
tests/
docs/
.agent-dispatch/
```

Do not create a new repository unless the current one demonstrably becomes an integration bottleneck.

## 13. Red-team of this plan

### RT1 — architecture expands faster than evidence

Risk:
- domain list becomes roadmap inflation.

Mitigation:
- only activate a lane when it has one bounded READY primitive or real-world question;
- inactive domains remain catalog entries, not infrastructure.

### RT2 — thin kernel becomes hidden universal IR

Risk:
- adapters leak domain semantics into shared fields.

Mitigation:
- kernel field admission rule: required by at least two domains and semantics identical in both.

### RT3 — duplicate extractors diverge

Risk:
- legacy/modern/domain adapters infer incompatible edges.

Mitigation:
- explicit adapter/version identity;
- differential fixtures;
- UNKNOWN over guessed normalization.

### RT4 — dynamic graph support becomes simulator rewrite

Risk:
- implementing command/piston transitions turns into an engine clone.

Mitigation:
- event receipts describe observed bounded transitions;
- vanilla remains execution oracle;
- simulate only when an independently qualified local model earns its keep.

### RT5 — parallel lanes contend on shared files

Risk:
- merge churn and accidental authority conflict.

Mitigation:
- isolated branches;
- lane-owned files;
- shared kernel/catalog reconciled serially.

### RT6 — workflow cost explodes

Risk:
- cross product of versions x domains x actors.

Mitigation:
- staged funnel;
- domain-scoped workflows;
- promotion matrix only after candidate maturity;
- no speculative full matrices.

### RT7 — actor qualification distorts mission work

Risk:
- tasks are chosen to benchmark actors rather than advance the project.

Mitigation:
- qualification is opportunistic only;
- mission task comes first;
- no extra ceremony unless a canonical oracle already exists.

### RT8 — same actor self-validates

Risk:
- correlated mistakes masquerade as consensus.

Mitigation:
- prefer independent deterministic validator;
- otherwise independent sibling reviewer actor;
- record when independence is unavailable.

### RT9 — multi-actor team overhead exceeds value

Risk:
- communication cost dominates bounded task.

Mitigation:
- default single actor;
- team rep only when task has separable author/reviewer/reconciler roles or meaningful heterogeneous capability.

### RT10 — corpus licensing contaminates repository

Mitigation:
- store citations/provenance;
- copy artifacts only when license permits;
- no unlicensed schematic/source vendoring.

### RT11 — edition creep

Risk:
- Java-specific semantics are accidentally generalized to Bedrock or other editions.

Mitigation:
- Java exact-version authority is explicit in every accepted contract;
- other editions remain separate discovery/comparison treatments until independently qualified.

### RT12 — branch-age illusion

Risk:
- a successful old child branch is integrated after the authority surface has changed.

Mitigation:
- current integration head is reconciled first;
- deterministic tests replay against that head;
- stale evidence remains provenance, not automatic acceptance.

## 14. Blue-team validation of the plan

The plan is accepted as efficient only if:

- current qualified Redstone lane can continue unchanged;
- a domain lane can fail without blocking unrelated lanes;
- one new domain can be added without modifying all others;
- exact-version provenance remains mandatory;
- full-matrix execution frequency does not increase for speculative work;
- shared-kernel changes are additive and reversible;
- promotion authority remains serialized;
- actor/team qualification cannot alter acceptance criteria;
- canonical GitHub/runtime evidence outranks actor claims;
- #381 WAIT remains respected.

## 15. Opportunistic actor qualification / interviews

Qualification is observational and piggybacks on real bounded work.

### Unit of qualification

Record separately:

- harness/framework;
- model;
- harness+model combination;
- execution resource/substrate;
- work-cell task class;
- authority envelope;
- tool set;
- result and canonical oracle.

Do not collapse these into one “agent quality” score.

### Eligible real task classes

- source/bytecode semantic recovery;
- literature/corpus synthesis;
- code implementation;
- static graph analysis;
- runtime failure diagnosis;
- test generation;
- independent review;
- evidence reconciliation.

### Single-actor interview

Use a real READY work cell with:

- explicit input refs;
- bounded authority;
- acceptance criteria;
- deterministic/runtime oracle where available;
- no hidden relaxed criteria.

Record a vector, not an aggregate rank:

- task completion state;
- correctness against oracle;
- evidence/provenance quality;
- scope discipline;
- number/type of corrective iterations;
- validator findings;
- resource realization;
- failure mode.

### Multi-actor team interview

Use only when the real task naturally decomposes.

Initial team patterns:

1. **author + independent reviewer**
2. **generator + validator**
3. **researcher + implementer + reconciler**
4. **two independent candidate actors + deterministic reconciler**

Constraints:

- depth 1 only;
- siblings do not recursively delegate;
- parent/orchestrator owns decomposition and reconciliation;
- team does not receive more authority than required;
- canonical project evidence decides acceptance.

Compare team results against a comparable single-actor baseline when naturally available; do not manufacture duplicate work solely for benchmarking.

### Opportunistic trigger

A work cell becomes a qualification rep when all are true:

- it is already mission-useful;
- the task class is identifiable;
- an external/deterministic/runtime oracle exists or can be bounded;
- actor identity/harness/resource can be recorded;
- recording evidence adds little marginal cost.

Otherwise execute the task normally without qualification overhead.

### Qualification non-interference rule

Qualification metadata:

- may never weaken a validator;
- may never cause an automatic retry;
- may never promote a candidate;
- may never expand authority;
- may never delay a critical-path fix solely to complete a benchmark.

## 16. Agent Dispatch deployment boundary

The repository already contains a public bootstrap workset and a WAIT leaf for live runtime proof.

For this plan:

- the checked-in cross-domain workset is **planning metadata only and non-executable** while #381 is WAIT;
- define planned delegations now;
- do not live project/plan/dispatch/observe via trusted host while #381 remains deferred;
- no Sidecar/grant mutation;
- once durable host authority is reactivated, READY domain work cells can become opportunistic qualification reps through the existing depth-1 model.

No recursive delegation.

## 17. Initial READY work

Without disturbing S0:

1. K1: draft additive causal-kernel-v1 schema only;
2. M1: source/runtime inventory for piston + sticky piston;
3. C1: consolidate existing command hooks into one bounded command primitive contract;
4. I1: bounded hopper/inventory-transfer primitive inventory;
5. O1: lamp terminal-vs-observed-state boundary as an electrical-owned observation surface;
6. R1: CORE 1.8.8 native-to-common projection design;
7. L1: multilingual corpus manifest with license/provenance fields;
8. Q1: extend metamorphic tests beyond same-net dust.

The four domain baselines E1/M1/C1/I1 remain independent. X1 cross-domain interaction work is WAIT until all four have bounded accepted baselines.

These can proceed independently on separate branches.

## 18. Stop / escalation conditions

Return blocked / needs-envelope-expansion when:

- a primitive requires unsupported paid compute;
- source identity/version cannot be established;
- an edge would require guessed semantics;
- licensing prevents intended artifact reuse;
- a cross-domain contract lacks one endpoint oracle;
- a task would require mutation of #381 WAIT authority;
- a proposed kernel field is domain-specific;
- a full matrix is being requested before staged falsification is complete.

## 19. Acceptance criteria for plan deployment

The first deployment tranche is successful when:

- this plan is reviewable without changing current runtime behavior;
- current qualified Redstone artifacts remain valid;
- at least three sibling lanes can execute independently;
- one bounded transducer reaches runtime qualification;
- no speculative lane triggers routine full matrices;
- dynamic-topology receipts can represent one piston move or command mutation without a universal simulator;
- actor qualification metadata is captured on at least one naturally occurring real work cell after live dispatch authority is available;
- at least one multi-actor team rep is captured only when a mission task naturally warrants it;
- all accepted results remain reconstructible from durable repository/workflow evidence.
