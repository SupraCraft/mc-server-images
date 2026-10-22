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

The synthetic negative suite covers false adjacency, reversed direction, mismatched/missing metadata, distant spoofed typed edges, malformed graph, privacy, unsupported source schema and aggregate signatures hiding distinct port topologies. These tests remain **unexecuted** until ordinary source/test qualification is admitted.

## Next independent original-world test (not yet authorized/executed)

1. Select one exact original-world physical component internally, preserving the coordinate-bearing original graph in a bounded ephemeral runner. Resolve actual sensor/excitation *from source*, not by guessing an input. If no controllable input exists, stop and record structural UNKNOWN.
2. Start **fresh copied** official Minecraft Java 1.8.8 worlds for sham/control and activation, with player embodiment where needed; loopback-only offline server. Do not modify base original save.
3. Before and after treatment, independently read piston base, extension/head, expected movable material state, and signal/repeater output; include an unpowered sham and at least one plausible negative. Require observed geometry change, not just saved piston metadata or arbitrary command state.
4. Capture bounded tick/time ordering and reset after stimulus removal. Missing movement in the observation window is a negative/inconclusive result, not proof that no related mechanism exists.
5. If original behavior qualifies, compare a separately version-pinned official Minecraft **26.3** physical realization against the same observable contract. Reuse existing piston acceptance (e.g. #27 original 26.3 source/runtimes), but do not claim equivalence by analogy.
6. Promote only with independent evidence and normal #27/#35 admission; require explicit rollback/provenance. Forward storytelling remains independent and consumes the result only if capability-qualified.

No bypass of safety-refused writes, private GHA spending, speculative Phase-B promotion, merged PR, TrueNAS mutation, or production deployment is part of this source-only work.
