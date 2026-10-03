# Legacy Uplift Parallel Execution Plan

Status: executable work plan  
Authority: `SupraCraft/mc-server-images#35`  
Related corpus authority: `#34`

## Objective

Exploit safe parallelism in Java 26.2 -> 26.3+ recovery/uplift work without wasting public/free GitHub Actions resources or creating competing semantic authorities.

The execution model is:

```
cheap static discovery lanes (parallel, bounded)
              |
              v
       evidence reconciliation
              |
              v
   one selected runtime question
              |
              v
 exact-version runtime qualification
              |
              v
 independent confirmation / promotion
```

Parallelism belongs in evidence generation. Promotion and shared-authority mutation remain serialized.

## Resource budget

### Static wave

- maximum simultaneous public GHA runners: **2**
- maximum static code-bearing lanes per wave: **3**
- per-lane timeout: **6 minutes**
- no Minecraft server boot
- no Docker/nested VM
- no GPU
- no package-install sweep
- no recursive workflow dispatch
- no automatic retry
- external repositories are shallow/pinned and used ephemerally
- upload only derived receipts, never restricted third-party source/world content
- superseded in-progress static waves may be cancelled

### Exact-runtime gate

- maximum simultaneous exact-runtime qualification: **1**
- runtime workflows are **manual/gated only**
- one generated-vs-maintainer pair per selected semantic question
- timeout: <=18 minutes
- exact Minecraft artifact remains pinned
- runtime is entered only when static evidence identifies a specific unresolved semantic question
- failed runtime attempts remain evidence; do not auto-retry

### Integration/promotion

- one reconciliation writer
- one rule-catalog promotion writer
- one shared-harness writer
- no concurrent semantic promotion
- no validator weakening
- #381 trusted-host/Sidecar boundary remains WAIT

## Wave 1

Three cheap lanes run with `max-parallel: 2`.

### Lane A — Sprint Racer residual clustering

Question:
What migration classes remain after applying the already-qualified Block State SNBT uplift?

Inputs:
- exact 26.2 commit `b674e09699818878749570760444ed7147fea3dc`
- exact 26.3 commit `93cdfcff9f2462313de4d568f169c0e442d94e42`

Outputs:
- exact changed `.mcfunction` count;
- files fully explained by Block State migration;
- files additionally explained by selector canonicalization/order;
- residual files that require another rule class;
- no automatic selector rewrite.

Purpose:
separate required compatibility work from style/performance modernization.

### Lane B — Voidblock structural residual

Question:
After the current generated 26.2->26.3 uplift, how much of the maintainer 26.3 overlay is byte-identical, structurally different, or genuinely new content?

Inputs:
- pinned Voidblock source `ea2dc4ea4eddb6ed4df10fa80ef418fd966b2e19`;
- current generic safe materializer;
- current worldgen uplift.

Outputs:
- generated/common/maintainer-only path counts;
- byte-identical common files;
- differing common files by extension/path family;
- no runtime boot.

Purpose:
identify the smallest next semantic differential rather than booting the server broadly.

### Lane C — uplift harness self-check

Question:
Is the current uplift machinery internally coherent before we spend runtime minutes?

Checks:
- Python compile;
- uplift unit tests;
- negative tests;
- rule catalog parse;
- workflow/tool presence.

Purpose:
fail fast on our own tooling before expensive qualification.

## Wave 1 reconciliation gate

The three lane receipts are merged into one derived summary.

The reconciler may choose at most **one** next runtime question.

Selection order:

1. blocker affecting correctness of accepted uplift;
2. repeated migration class seen in >1 independent artifact;
3. structural reimplementation with a cheap bounded oracle;
4. candidate modernization only if it materially improves the product/harness.

If no candidate clears that bar, no runtime job is launched.

## Wave 2 candidate runtime

Current expected candidate:

- Voidblock: one bounded worldgen semantic family from the remaining differing common files.

Do **not** attempt arbitrary-seed whole-world equivalence first.

Preferred sequence:
1. one carver or density-family observable;
2. deterministic fixture/seed;
3. generated uplift vs maintainer 26.3;
4. hard negative;
5. exact-runtime receipt.

## Wave 3 independent generalization

Parallel static lanes may then target:
- another exact 26.2/26.3 project;
- a second serialization surface;
- another command/datapack migration family.

A rule becomes U5 only after:
- at least two independent artifacts/projects where relevant;
- no unexplained conflicting evidence;
- serialization-surface scope is explicit;
- negative cases are preserved.

## Red team

### Failure: CI fan-out burns free minutes
Mitigation:
- heavy runtime workflows manual-only;
- static wave max-parallel=2;
- path-scoped triggers;
- `cancel-in-progress: true` for superseded static waves;
- no cron.

### Failure: duplicate work
Mitigation:
- exact pinned authorities in each lane;
- derived receipts keyed to exact commits;
- reconciler selects one follow-on runtime question;
- known-negative v1 runtime remains manual-only.

### Failure: race on shared authority
Mitigation:
- discovery lanes do not write the canonical catalog/workset;
- one serialized reconciliation writer;
- promotion occurs after wave completion.

### Failure: static similarity mistaken for semantic equivalence
Mitigation:
- static lanes can nominate but not promote structural rules;
- runtime required for semantic-changing reimplementations;
- bounded claims only.

### Failure: third-party licensing leakage
Mitigation:
- ephemeral checkouts;
- derived counts/hashes/receipts only;
- no uploaded raw source/world content;
- source license boundary recorded.

### Failure: retries turn into score chasing
Mitigation:
- no automatic retry;
- failed runs remain hard negatives;
- rerun only after a diagnosed code/test correction.

### Failure: parallelism creates noisy partial answers
Mitigation:
- deterministic final reconcile job;
- lane outputs are machine-readable;
- partial lane failure does not cancel independent lanes.

## Blue team

The plan is effective because:

- two runners provide useful overlap without a five-runner burst;
- static analysis extracts most migration information at far lower cost than server boots;
- exact runtime is reserved for questions static evidence cannot answer;
- Sprint Racer and Voidblock exercise different implementation surfaces;
- existing U4 evidence is reused rather than rerun gratuitously;
- derived receipts make later reconciliation cheap;
- the architecture preserves independent failure domains and causal attribution.

## Stop conditions

Stop a lane when:
- its bounded question is answered;
- the next step requires semantic runtime evidence;
- evidence duplicates an existing accepted receipt;
- licensing/provenance prevents further analysis;
- cost exceeds the expected information gain.

Stop a wave when:
- all lane receipts exist or have preserved failures;
- reconciler has selected zero or one runtime follow-up.

## Current execution

Wave 1 is authorized by the user's instruction to document, implement, and execute this plan.

Runtime qualification remains gated by Wave 1 evidence and will not be launched merely to keep runners busy.
