# World Generator Benchmark — Autonomous Implementation & Deployment Plan

Status: proposed implementation authority for the public/free execution harness  
Design authorities:
- `SupraCraft/mc-structure-foundry-private#6`
- `SupraCraft/mc-reversing-lab-private#196`
Public execution authority:
- `SupraCraft/mc-server-images#11`

## 1. Intent

Build a reproducible, autonomous benchmark and experimentation system for Minecraft Java 26.3 world generators and generator pipelines.

The system must:
- compare deterministic, stochastic, rule/grammar, WFC, procedural, learned/diffusion, and hybrid generators;
- generate downloadable playable worlds;
- automatically analyze terrain, biomes/ecology, resources, structures, spawns, affordances, progression, performance, and visual-interest candidates;
- generate bot/camera tours that include interesting, dull, representative, spawn/progression, ecology/resource, and defect/anomaly sites;
- support purpose-specific generator stacks and order/ablation experiments;
- preserve per-dimension metrics and quality-diversity/Pareto views rather than an authoritative scalar winner;
- let humans focus review on high-information sites and traces.

## 2. Non-negotiable execution boundary

All GitHub-hosted execution for this effort MUST occur in public repositories on standard GitHub-hosted runner classes.

Hard constraints:
- no private-repository GitHub-hosted Actions;
- no paid/larger GitHub runners;
- no `*-large`, `*-xlarge`, or billed GPU labels;
- every executable benchmark workflow fails closed when `github.event.repository.private != false`;
- hard money budget = USD 0 for every Agent Dispatch delegation;
- no automatic paid fallback;
- no recursive delegation;
- no unbounded retry loops;
- no generic queue/scheduler/database service;
- provider credentials must not be exposed to pull-request/fork-controlled code;
- model bytes are never vendored into Git merely for convenience.

Public Actions are used only for the public benchmark project itself: build, test, generation, analysis, visualization, qualification, packaging, and project operation. They are not a proxy compute service for unrelated private work.

## 3. Authority and control topology

```
private design / acceptance authority
  mc-structure-foundry-private#6
  mc-reversing-lab-private#196
             |
             | public-safe bounded projection
             v
public benchmark authority
  mc-server-images#11 + code/contracts
             |
             v
Agent Dispatch
  projection -> target binding -> dispatch -> observe
             |
       +-----+-------------------+
       |                         |
       v                         v
public GHA deterministic     free hosted coding/
execution                    reasoning actors
       |                         |
       +-----------+-------------+
                   v
        candidate code/results
                   |
                   v
       independent validators
                   |
                   v
 public artifact/PR/evidence state
                   |
                   v
 private authority reconciliation
```

Agent Dispatch remains the common actuator/observer. It does not become a scheduler or project authority.

## 4. Concrete free execution substrates

Initial qualified/substrate candidates:

### Public Ubuntu x64
Primary lane for:
- Java 25 Minecraft servers;
- Docker/Podman-compatible container builds;
- CPU model inference;
- region/NBT analysis;
- FFmpeg;
- Python/Java/Node tooling;
- deterministic validators;
- vanilla/custom/datapack generator worlds.

Use standard public Ubuntu runner classes only.

### Public Ubuntu ARM64
Secondary portability lane for:
- container/runtime portability;
- native ARM64 utilities;
- architecture-neutral analyzer qualification.

Do not spend ARM reps unless portability evidence is useful.

### Public macOS 26 ARM64
Specialized lane for:
- Apple Silicon/CoreML inference;
- Terrain Diffusion;
- Metal/CoreML qualification;
- selected renderer/toolchain portability checks.

Current observed benchmark evidence:
- M1 virtual runner;
- CoreML loads;
- Metal device exposed as Apple Paravirtual device;
- PyTorch MPS Conv3d is not currently a valid Dream-Cubed acceleration path;
- Terrain Diffusion CoreML pipeline has completed successfully.

### Free hosted agent/model actors
Use only already-qualified or newly qualified free actors for bounded development/review tasks:
- Google Jules where free quota/admission is available;
- OpenRouter free-model treatments for discovery/critique/non-critical generation;
- qualified Goose/OpenWorker/Codex-style harnesses only when their underlying execution/resource path is free for this task.

Critical project acceptance must not depend on the availability of any one free model/provider.

## 5. Repository layout

Do not create another repository until the public benchmark has outgrown `mc-server-images`.

Proposed layout:

```
bench/worldgen/
  schemas/
  adapters/
    vanilla/
    tectonic/
    wwoo/
    terrain_diffusion/
    dreamcubed/
    build_with_bombs/
  pipelines/
  analyzers/
  personas/
  saliency/
  tour/
  validators/
  controls/
  campaigns/
  reports/
tools/
.github/workflows/
docs/
.agent-dispatch/
```

Container entrypoints must also run locally with Docker/Podman and later under TrueNAS/GARM without changing experiment semantics.

## 6. Canonical contracts

Implement these versioned contracts before expanding the generator matrix.

### generator-adapter-v1
Declares:
- generator ID/version;
- exact source/artifact provenance;
- supported Minecraft version;
- seed semantics;
- required runtime capabilities;
- input/config schema;
- produced representation;
- semantic layers owned;
- layers preserved;
- redistribution/license constraints.

### generator-pipeline-v1
Declares:
- ordered stages;
- stage configs/seeds;
- semantic ownership;
- preserve masks;
- permitted overwrite domains;
- validation gate after each stage;
- purpose/gameplay profile.

### worldgen-run-v1
Per generated world:
- run/campaign ID;
- adapter/pipeline identities;
- exact revisions/hashes;
- seed/scenario;
- runner/resource realization;
- timings and resource observations;
- output hashes;
- failure/partial state.

### worldgen-analysis-v1
Separate sections:
- feasibility;
- terrain geometry;
- biome/ecology;
- resources/progression;
- structures/architecture;
- spawn potential/runtime observations;
- affordances/discoverability;
- persona traces;
- performance;
- visual/saliency features;
- anomalies.

No authoritative aggregate score.

### worldgen-tour-v1
Every selected site records:
- coordinates;
- selection category;
- reasons/features;
- camera target/path;
- teleport command;
- related metrics;
- screenshots/video segment references.

Required categories:
- top-interest;
- bottom/dull;
- representative;
- anomaly/defect;
- spawn/progression;
- ecology/resource;
- random/stratified control.

## 7. Multi-fidelity evaluation funnel

Do not run the most expensive analysis on every candidate.

```
generator
  -> artifact/provenance validation
  -> hard feasibility
  -> cheap static analysis
  -> multi-scale world analysis
  -> runtime spawn/ecology probes
  -> persona playtests
  -> visual/saliency inference
  -> camera tour/video
  -> QD/Pareto archive
  -> human review
```

A failing candidate may still be retained as a negative control or repair candidate, but must be labeled.

## 8. Initial automated metrics

### Hard feasibility
- world boots on official/qualified 26.3 runtime;
- no corrupt chunk/region data;
- valid player spawn;
- minimum traversable area;
- generator-declared hard invariants;
- required progression resources/affordances not provably impossible.

### Terrain
- elevation distribution;
- local relief;
- slope/curvature;
- prominence;
- ruggedness;
- water/land interfaces;
- accessible-surface fraction;
- cave/open-volume connectivity;
- floating/disconnected anomalies;
- multi-scale repetition/autocorrelation.

### Biome/ecology
- biome adjacency graph;
- transition frequency;
- fragmentation;
- ecotone/abrupt-transition measures;
- climate-distance continuity where semantics permit;
- biome/terrain correspondence;
- vegetation/material consistency;
- water/terrain/ecology consistency.

### Resources/progression
- resource counts/density by biome/depth;
- nearest-resource distances;
- path/travel cost from spawn;
- early survival bundle availability;
- reachability;
- scarcity/abundance anomalies;
- progression-affordance distances.

### Structures/architecture
- connected components;
- support/floating defects;
- enclosure/interior-volume proxies;
- entrances/accessibility;
- roads/paths;
- terrain adaptation;
- structure collisions;
- palette/repetition/diversity;
- loot/workstation/farm affordances.

### Spawn/ecology runtime
Separate:
1. static spawn potential;
2. observed controlled-runtime behavior.

Measure:
- player spawn safety;
- passive/hostile spawnable area;
- pathable area;
- biome/environment compatibility;
- suppression/amplification anomalies.

### Discoverability
- line-of-sight/proxy visibility;
- topographic prominence;
- route/path distance;
- entrance visibility;
- landmark density;
- exploration opportunity density;
- hidden-secret vs accidental-undiscoverability classification.

### Performance
- worldgen latency/chunk or bounded region;
- peak memory;
- output size;
- server tick impact where measurable;
- cold/warm generation distinction.

## 9. Persona playtesting

Initial standardized personas:
- cautious survivalist;
- progression optimizer;
- explorer/landmark seeker;
- resource gatherer/builder;
- spelunker;
- combat/hostile-encounter seeker.

Each persona emits:
- objective;
- observation/action trace;
- path;
- discoveries;
- resource acquisition;
- hazards/deaths;
- time/distance/action cost;
- terminal state.

No single persona supports a broad playability claim.

## 10. Visual-interest triage

Use a fusion of independent detectors rather than one aesthetic model:

- geometric prominence/relief;
- unusual biome/ecotone;
- water/terrain interfaces;
- structure density/rarity;
- resource/progression significance;
- anomaly/defect score;
- rendered-view embedding novelty/diversity;
- optional registered SigLIP2/vision model from Model Artifact Foundry.

The vision model nominates sites; it does not decide objective quality.

Human review remains authoritative for aesthetic preference.

## 11. Quality-Diversity and feasibility

After the metric vector is stable:

- hard feasibility is separate from quality/preference;
- retain feasible and near-feasible/infeasible archives;
- expose behavior descriptors such as:
  - verticality;
  - wilderness/settlement density;
  - resource scarcity;
  - biome diversity;
  - travel difficulty;
  - landmark density;
  - cave accessibility;
  - architecture density;
  - ecological coherence.

Later MAP-Elites/FI-MAP-Elites work consumes existing receipts; it does not redefine the benchmark.

## 12. Generator rollout order

### Controls / baseline
1. superflat/null control;
2. deliberately noisy/corrupted synthetic control;
3. vanilla 26.3 normal;
4. vanilla amplified;
5. vanilla large-biome / single-biome controls where 26.3 supports them.

### Deterministic/procedural
6. Tectonic 26.3;
7. WWOO 26.3;
8. Tectonic + WWOO;
9. additional 26.3-compatible generators only after license/version qualification.

### Architecture/settlement
10. vanilla structures/jigsaw;
11. qualified Towns & Towers / Structory / Dungeons & Taverns;
12. portable GDMC generators;
13. WFC/grammar/template systems.

### Learned
14. Terrain Diffusion;
15. Dream-Cubed;
16. Build-with-Bombs;
17. Scaffold Diffusion only when a reproducible checkpoint/training route is established.

## 13. Hybrid/composition experiments

Every stage must declare:
- owned semantic layer(s);
- protected layer(s);
- allowed overwrite scope;
- pre/post hashes;
- semantic/world diff;
- validation delta;
- cost/latency.

Initial sequence ablations:
- vanilla terrain -> GDMC/WFC settlement -> Dream-Cubed local detail;
- grammar skeleton -> diffusion detail -> deterministic repair;
- Terrain Diffusion -> hydrology/ecology/resource repair -> structures;
- vanilla/Tectonic terrain -> learned structure generation;
- structure-first -> terrain conditioned around fixed structure.

Always test meaningful order reversal when technically possible.

## 14. Agent Dispatch work model

Use a sequence of bounded worksets, not one permanent mega-workset.

### Bootstrap workset
Goal:
- contracts + public-only guards;
- generic adapter interface;
- vanilla normal + superflat;
- canonical world artifact;
- deterministic validator;
- one Agent Dispatch -> public GHA -> result round trip.

### Analyzer workset
Goal:
- static terrain/biome/resource/structure metrics;
- negative controls;
- multi-scale windows.

### Tour workset
Goal:
- playable world packaging;
- teleport manifest;
- camera bot;
- MP4/contact sheet.

### Ecology/playability workset
Goal:
- runtime spawning;
- resource/progression probes;
- persona suite.

### Generator-expansion worksets
One bounded adapter family per workset.

### Hybrid/QD worksets
Only after base adapters and metrics are trustworthy.

Parent actors may use already-qualified **depth-1 delegation only**. Recursive delegation remains disabled.

## 15. Autonomous development loop

For each bounded implementation cell:

```
authoritative issue/workset
    -> orchestrator selects highest READY cell
    -> Agent Dispatch derives least-authority projection
    -> free qualified generator actor implements candidate
    -> public GHA deterministic tests/qualification
    -> independent validator actor or deterministic oracle
    -> project-native acceptance/reconciliation
    -> durable result/baton
    -> next READY cell
```

Rules:
- first returned candidate is preserved for qualification evidence;
- generator and validator should be distinct where practical;
- no validator weakening to accept a candidate;
- failure returns actionable evidence;
- no automatic retries unless explicitly budgeted;
- ordinary in-envelope work does not require human approval;
- merge/release authority stays reserved during the bootstrap campaign.

After several clean reps, a later workset may separately qualify limited auto-merge for allowlisted low-risk public benchmark paths.

## 16. Agent Dispatch target deployment

Configure host-side Agent Dispatch targets; target identity stays below workset semantics.

### Target A: public Linux benchmark
Capabilities:
- `public-minecraft-worldgen`
- `linux-x64`
- `github-actions`
- `docker`
- `java25`
- `python`
- `node`
- `ffmpeg`

Binding:
- repository: `SupraCraft/mc-server-images`
- approved workflow: benchmark execution workflow on `main`
- standard public Ubuntu runner only.

### Target B: public Apple/CoreML benchmark
Capabilities:
- `public-minecraft-worldgen`
- `macos-arm64`
- `coreml`
- `metal-observed`
- `terrain-diffusion-runtime`

Binding:
- repository: `SupraCraft/mc-server-images`
- approved workflow: CoreML benchmark workflow on `main`
- standard `macos-26` only.

### Development actor targets
Reuse qualified hosted-agent adapters rather than create a new provider layer.
Capability examples:
- `public-repository-code-edit`;
- `public-repository-review`;
- `research-synthesis`;
- `python-java-yaml`.

No paid fallback.

## 17. Workflow security / spend guards

Every benchmark workflow:
- checks repository is public;
- has an allowlist of standard runner labels;
- uses fixed/allowlisted adapter IDs rather than arbitrary commands;
- pins or hashes upstream generator/model artifacts;
- uses minimal `permissions`;
- never exposes provider/model API keys to fork/PR-controlled code;
- records exact runner label/image facts;
- enforces bounded timeouts;
- emits machine-readable terminal receipts.

Workflows that need provider credentials must be trusted-branch/manual-dispatch only and must not execute untrusted checked-out code.

## 18. Model Artifact Foundry integration

Every learned artifact consumed by the benchmark must have:
- logical Foundry ID;
- provider/source;
- exact revision;
- exact file hash;
- license/rights state;
- runtime format;
- experiment consumer references.

Model registration does not imply promotion.

Reference-only/unclear-license artifacts remain provider-native and are never mirrored merely for convenience.

## 19. Deployment stages

### D0 — Plan + workset projection
- land contracts/plan;
- configure Agent Dispatch public benchmark targets;
- prove public-only guard.

### D1 — Minimal round trip
- Agent Dispatch dispatches one vanilla/superflat public job;
- normalize terminal result;
- no private Actions use;
- canonical artifact receipt passes.

### D2 — World materialization
- repair generic 26.3 playable-world packaging;
- world zip opens;
- Creative/Spectator/teleports work.

### D3 — Analyzer
- static multi-scale analyzers;
- negative controls behave sensibly.

### D4 — Presentation
- bot/camera tour;
- MP4/contact sheet;
- interesting/dull/representative/anomaly selection.

### D5 — Generator matrix
- vanilla/Tectonic/WWOO/Tectonic+WWOO;
- learned lanes already proven at inference level are integrated.

### D6 — Ecology/playability
- resources;
- spawn potential/runtime;
- personas;
- progression.

### D7 — Hybrid experimentation
- stage ownership/preservation;
- order permutations;
- ablations;
- repair passes.

### D8 — QD campaign
- behavior descriptors;
- feasible/infeasible archives;
- frontier selection;
- human inspection workflow.

## 20. Bootstrap critical path

Highest READY order:

1. define versioned schemas + adapter CLI;
2. add public-only/standard-runner validator;
3. implement vanilla 26.3 + superflat adapters;
4. produce canonical downloadable world + receipt;
5. repair/qualify world materializer;
6. implement static analyzer skeleton;
7. implement deterministic site-selection controls;
8. implement tour manifest + camera path;
9. wire Agent Dispatch target + one-dispatch workset;
10. execute one full round trip and independently validate it.

Parallel after step 2:
- 26.3 worldgen extraction in `mc-reversing-lab-private#196`;
- Dream-Cubed mapping/materialization adapter;
- Terrain Diffusion world adapter;
- Model Artifact Foundry registration/evidence maintenance.

## 21. Bootstrap acceptance criteria

Bootstrap is accepted only when:

- no private GitHub Actions run is required;
- public workflows fail closed in a private repository;
- only standard public runners are used;
- Agent Dispatch binds and dispatches one approved public benchmark target;
- vanilla 26.3 and one negative/control world produce canonical receipts;
- at least one world is downloadable and opens in Minecraft 26.3;
- teleport/tour manifest exists;
- analyzer produces deterministic machine-readable output;
- independent validation catches the intentionally bad control;
- result can be reconstructed from GitHub/receipts without chat history;
- USD spend is zero;
- no queue/scheduler/database has been added.

## 22. Stop / escalation conditions

Return `needs-envelope-expansion` rather than violating the envelope when:
- a method requires paid GPU/larger runner;
- a required model artifact is gated/unavailable;
- a license forbids intended use/redistribution;
- public Actions would require private project material;
- a workflow needs secrets exposed to untrusted code;
- a benchmark assertion cannot be independently validated;
- resource use exceeds bounded workflow limits.

Do not silently substitute a different model, version, generator, runner, or reduced-quality algorithm and call it the same experiment.
