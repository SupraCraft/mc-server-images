# CORE 1.8.8 electromechanical gameplay — directional witness qualification

Status: **static discovery candidate only; native piston actuation NOT RUN**.

Authority and consumption: [CORE corpus DLE #34](https://github.com/SupraCraft/mc-server-images/issues/34), [causal machinery #27](https://github.com/SupraCraft/mc-server-images/issues/27), [legacy uplift #35](https://github.com/SupraCraft/mc-server-images/issues/35), [forward private MCWORLD #17](https://github.com/SupraCraft/mc-structure-foundry-private/issues/17). Candidate source on *separate* public draft PR #107; never reroute the unrelated refused PR #108 attribution workflow.

## Source-derived evidence (not gameplay proof)

- CORE by UnlikelyWaffle v1.4, original Java 1.8.8, CC BY-SA 4.0. Its independently accepted original input SHA256 is `61092508c78f5dbe36b03a9d0bdb202c5ddfe71f1aada58d62ae81ae93f5a998`.
- Canonical **derived graph SHA256** from public CORE motif run 39696702260: `5a5c25a31e2bcdec1f2d7d18cc4dedfc87c5a43e53cab4529e5bcdac0452efb5`. No raw world, region, source commands or private graph should be published.
- Priority existing aggregate signature `2481c9098598b179b312d89dd7ef1d03b2401a2b1ae84dee5908e0eb6be50794`, 2 physical-component occurrences, nominal families: five redstone wires, one inactive repeater, one sticky piston. Existing counts include 8 `direct_redstone_edges` and 2 `oriented_signal_candidates` **per aggregate signature**.
- **Crucial boundary:** `direct_redstone_edges` may refer solely to wire→wire. `oriented_signal_candidates` can represent repeater input rather than an output connected to the piston. These edge collections cannot by themselves establish a powered or even source-directed actuator.

## New candidate scanner

`tools/rank_legacy_electromechanical_witnesses.py` consumes only the complete, already produced `supracraft-legacy-causal-machinery/1` JSON, requiring its exact frozen SHA256. No server, world regeneration, network or command dispatcher is used.

On an **already admitted original-world custody runner**:

```bash
python -m tools.rank_legacy_electromechanical_witnesses \
  --graph ephemeral/core-original-causal.json \
  --expected-graph-sha256 5a5c25a31e2bcdec1f2d7d18cc4dedfc87c5a43e53cab4529e5bcdac0452efb5 \
  --signature 2481c9098598b179b312d89dd7ef1d03b2401a2b1ae84dee5908e0eb6be50794 \
  --output derived/core-electromechanical-typed-candidate.json

python -m unittest discover -s tests \
  -p test_rank_legacy_electromechanical_witnesses.py -v
```

If the graph digest differs, **stop and investigate**; do not silently update the pinned digest or substitute a different original map. The output reports only aggregate family/edge counts and inferred typed-edge candidate classes; no raw source positions, command text, actor identifiers, world copies, or coordinate-derived node hashes. A given legacy motif signature may split into multiple **directional subtypes**, because aggregate counts do not encode actual circuit topology.

Allowed static diagnoses, never automatic promotions:
- `DIRECT_DUST_TO_PISTON_STATIC_CANDIDATE`: a typed potential horizontal wire→piston edge, with original node positions verifying adjacency.
- `ORIENTED_REPEATER_TO_PISTON_STATIC_CANDIDATE`: typed front repeater→piston edge, consistent with original repeater facing metadata.
- `NO_NAMED_PISTON_INPUT`: no witnessed typed direct-port edge inside this scanner's bounded model. **Not evidence of no mechanism**: hidden solid-block conduction, quasi-connectivity, vertical support, world update order and chunk state are out of scope.

The synthetic negative suite covers false adjacency, reversed direction, mismatched/missing metadata, distant spoofed typed edges, malformed graph, privacy, unsupported source schema and aggregate signatures hiding distinct port topologies. The 21 baseline/head-face synthetic controls passed at run 39948192364; subsequent upstream tests passed at run 39951784831. Later additional coordinate-spoof hard negatives require their own exact-head run receipt in #34.

## Latest exact-graph qualification and native-stimulus preflight (2026-10-23)

- Public source-only test at [run 39951784831](https://github.com/SupraCraft/mc-server-images/actions/runs/39951784831): 10 motif + 27 original-era port/upstream-sensor hard negatives PASS at exact source head 957d0475b61436ede0b1a0813ab706ba96955a3c.
- [Run 39948430956](https://github.com/SupraCraft/mc-server-images/actions/runs/39948430956) reconstructed the frozen complete CORE v1.4 1.8.8 graph from exact SHA-pinned CC-BY-SA source; 2 instances in 1 priority signature subtype have 1 named wire-to-repeater rear input, 1 repeater-front-to-piston port, 0 direct dust-to-piston candidates, per instance. This is static named port **evidence**, not actual powered state.
- The source motif consists of five redstone wires, one unpowered repeater, and one sticky piston in each component. It contains no local sensor node. The input readiness extension now traces *only named, original-coordinate-consistent wire edges backward* from typed sink ports and tests whether a recognized local sensor is connected to the traced dust. `NO_NAMED_LOCAL_SENSOR_ON_TYPED_WIRE_PATH` means **only** that the current extractor has no named local sensor-to-rear path; it must not be interpreted as no possible manual, solid-mediated, remote-programmed or quasi-connected excitation.
- The input checker does not inject source commands, guess switch coordinates, modify the original save, prove piston motion, or replace independently licensed original-version and player/HIL qualification. Synthetic controls explicitly reject forged remote edges, reversed sensor direction, absent repeater rear and distant/coordinate-spoofed physical adjacency.
- Any emitted `upstream_named_wire_count` and `upstream_named_sensor_count` are derived **aggregate counts only**; never export original world positions, source commands, node IDs or reversible coordinate hashes. Native stimulus/root selection must remain internal to an independently admitted original-world workcell.
- Once exact-head updated tests and graph scan complete, link their immutable run/job/artifact SHA receipts in [#34](https://github.com/SupraCraft/mc-server-images/issues/34). No source status field is a gameplay primitive admission.

## Saved original-world power-neighbor qualification (2026-10-23)

The source-only pinned-CORE [run 39953417745](https://github.com/SupraCraft/mc-server-images/actions/runs/39953417745) qualified `tools/inspect_legacy_piston_snapshot_inputs.py` against the exact original CORE v1.4 ZIP and the identical frozen causal graph. It selected both piston components internally by the existing immutable motif signature, independently required count parity with the directional ranker, then read only the **six-face block neighbors of their 10 wire occurrences** in the stopped original 1.8.8 Anvil data. No server, client, player, original save modification, source command execution, or raw-coordinate egress occurred.

Observed **60 of 60** neighbor contacts resolved from saved NBT; **zero** were legacy redstone block ID 152, lit or unlit redstone torches, levers, buttons or pressure plates. Result: `NO_SAVED_ADJACENT_REDSTONE_BLOCK_IN_SAMPLED_SIX_FACES`. The independent derived-only artifact is [12501850680](https://github.com/SupraCraft/mc-server-images/actions/runs/39953417745), ZIP SHA256 `2a4f911dc2c47ff9be1bcc7ab4ff595f5c3e60da0d15585d9411d46bb82f1963`, expires 2026-11-06 UTC. Exact public synthetic [run 39953258559](https://github.com/SupraCraft/mc-server-images/actions/runs/39953258559) passed **47/47** source-free tests (10 motif, 29 ranker, 8 saved-block inspector).

**Limits:** This is an original *saved snapshot* and only immediate six-face contacts to dust. It does **not** prove absence of indirectly powered solid blocks, scheduled command-world mutation, quasi-connectivity, or a source activated only by an actual player or tick. It does **not** prove piston motion. Do not turn a static negative into an absence-of-gameplay claim. The next ordinary native approval gate remains separate; only a fresh copied official original Java 1.8.8 world with real sham/excitation readback can establish actuation and later 26.3 parity.

## Command-authored world mutation and circuit-copying recovery (2026-10-23)

Additional **independent static** scans on the SHA-pinned CORE v1.4 original source and frozen graph preserve full source custody and DLE #34 authority, without execution or raw source redistribution.

- [Source-only synthetics 39984283357](https://github.com/SupraCraft/mc-server-images/actions/runs/39984283357): **85/85 PASS** in six groups (10 existing motifs; 29 ranker; 8 saved-block; 18 source-command/spatial hard negatives; 11 clone material; 9 clone mode/fingerprint). The intermediate red test [39983064025](https://github.com/SupraCraft/mc-server-images/actions/runs/39983064025) was a stale UNKNOWN-text assertion, corrected and rerun to green; it did not indicate failure of a native gameplay mechanic.
- [Source-authored mutation census 39983273253](https://github.com/SupraCraft/mc-server-images/actions/runs/39983273253) at an earlier source head found **428** compact `setblock` writes with **zero** redstone-block direct contact matches against 50 unique six-face candidate wire-input positions; resolved 69 `fill` and 26 `clone` destination footprints, and **two clone commands** with a possible overlap. Unresolved `execute` count 23 and one unresolved `fill` bound, among 119 broadly unsupported spatial/dynamic command records. A clone destination footprint is a hypothesis about potential writes, **not observed execution**.
- [Pinned original clone material scan 39983835998](https://github.com/SupraCraft/mc-server-images/actions/runs/39983835998) independently sampled **50/50** original saved source cells corresponding to selected clone destination/contact intersections. Source class counts: **22 air, 16 other saved block IDs, 10 redstone wire, 2 unpowered repeaters**, and **zero redstone-block source cells**. The absence of a redstone block in these cells does not disprove an indirect or runtime-generated source.
- [Exact source-fingerprinted original clone modes 39984407368](https://github.com/SupraCraft/mc-server-images/actions/runs/39984407368) verified both original command block tile entities against the graph's frozen command SHA256 identities: **2/2 matches**, modes **`replace` ×2** and **`normal` ×2**, with **no raw command text export**. Hence these commands are authored to copy their source volume using replace semantics, including air cells if executed as represented. Neither observed command activation nor actual restored/moved blocks have been measured.
- The latest derived-only original-custody [artifact 12514328178](https://github.com/SupraCraft/mc-server-images/actions/runs/39984407368) SHA256 `99e46df39efcc9bd30a02fadf208f1fb6012c81dcb5d5c88637065a00b424d92`, expires **2026-11-06 16:09:48 UTC**, contains aggregated, attributed JSON only; original world, source graph, coordinates and command strings never shipped.

**Interpretation:** the map author explicitly included **two source-fingerprinted clone operations configured as replace/normal** whose bounded destination geometry potentially intersects the two static electromechanical components. Saved clone-source materials include electrical circuit blocks. This identifies a credible **circuit reconstruction / reconfiguration / reset *candidate***. Its purpose, live execution trigger, resulting motion, 1.8.8 state transitions and exact Java 26.3 gameplay port are **NOT PROVEN**. Candidate Story/Game IR promotion, native server/player intervention, merged PR and production deployment remain separate authority gates.

**Next source-safe discriminator:** compare each clone's *mapped source state* with the saved original *destination state* for the exact overlapping contacts. Quantify only aggregate possible material deltas, distinguish already-identical geometry from potential circuit restoration, and retain any unresolved original command conditions. After that source-only evidence, obtain separate ordinary admission for official fresh-copy Java 1.8.8 paired stimulus/readback; until then, **no native gameplay PASS claim**.

## Next independent original-world test (not yet authorized/executed)

1. Select one exact original-world physical component internally, preserving the coordinate-bearing original graph in a bounded ephemeral runner. Resolve actual sensor/excitation *from source*, not by guessing an input. If no controllable input exists, stop and record structural UNKNOWN.
2. Start **fresh copied** official Minecraft Java 1.8.8 worlds for sham/control and activation, with player embodiment where needed; loopback-only offline server. Do not modify base original save.
3. Before and after treatment, independently read piston base, extension/head, expected movable material state, and signal/repeater output; include an unpowered sham and at least one plausible negative. Require observed geometry change, not just saved piston metadata or arbitrary command state.
4. Capture bounded tick/time ordering and reset after stimulus removal. Missing movement in the observation window is a negative/inconclusive result, not proof that no related mechanism exists.
5. If original behavior qualifies, compare a separately version-pinned official Minecraft **26.3** physical realization against the same observable contract. Reuse existing piston acceptance (e.g. #27 original 26.3 source/runtimes), but do not claim equivalence by analogy.
6. Promote only with independent evidence and normal #27/#35 admission; require explicit rollback/provenance. Forward storytelling remains independent and consumes the result only if capability-qualified.

No bypass of safety-refused writes, private GHA spending, speculative Phase-B promotion, merged PR, TrueNAS mutation, or production deployment is part of this source-only work.
