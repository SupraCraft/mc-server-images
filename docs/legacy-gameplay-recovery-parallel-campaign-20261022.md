# Legacy Gameplay Recovery: parallel bounded discovery cell (2026-10-22)

Status: **CANDIDATE / DO NOT PROMOTE**. Source-only additive cell.
Canonical execution/evidence authorities: [external corpus #34](https://github.com/SupraCraft/mc-server-images/issues/34), [cross-domain causal microscopy #27](https://github.com/SupraCraft/mc-server-images/issues/27), [legacy uplift #35](https://github.com/SupraCraft/mc-server-images/issues/35), [public oracle #11](https://github.com/SupraCraft/mc-server-images/issues/11).
Forward storytelling remains owned by [MCWORLD #17](https://github.com/SupraCraft/mc-structure-foundry-private/issues/17) and [Lantern #19](https://github.com/SupraCraft/mc-structure-foundry-private/issues/19). This document does not supersede their DLE records.

## Purpose

Recover reusable *gameplay behavior* from existing Minecraft worlds, not just block catalogs, and run as an independent, concurrent producer of candidate capabilities for MCSTORY/MCWORLD. Reuse existing analyzers and independent oracles. Discovery does not authorize world mutation, rewrite, corpus redistribution, gameplay acceptance, or release.

## Existing accepted and candidate evidence

- CORE v1.4 1.8.8 legacy-world four-domain census: electrical 2,572; programmable 1,445; inventory 1,086; mechanical 110; mixed-domain adjacency components 403. These are NOT 403 qualified transducers (see #27 comment 5970143217).
- Sprint Racer 26.3 physical sample: 6,068 chunks decoded with zero parser errors in corrected native-format reader; gameplay causal behavior not proven by static census (#34 comment 5973816445).
- Independent 26.3 bounded primitive tests exist for selected redstone, mechanical piston push limit, hopper, and command operation. Their *compositions* are separately gated (#27).
- Existing Voidblock and Sprint Racer 26.2->26.3 uplift qualification remains owned by #35; do not infer full gameplay parity from bounded tests.
- The source-recovery and engine capability authority remains mc-reversing-lab-private #104, #252 and #253.

## Additive candidate-discovery tool

Input: the complete `supracraft-legacy-causal-machinery/1` JSON already emitted by
`tools/analyze_legacy_causal_machinery.py`. Do not re-decode the third-party world.
Tool: `tools/classify_legacy_gameplay_motifs.py`.

Command (on an already admitted public-safe derived graph):

```bash
python tools/classify_legacy_gameplay_motifs.py \
  --graph /path/to/legacy-causal-graph.json \
  --output /tmp/legacy-gameplay-candidates.json
python -m unittest discover -s tests -p 'test_classify_legacy_gameplay_motifs.py' -v
```

Result is *derived aggregate metadata only*: family/domain counts, counted named candidate-edge types, signature digest, occurrence count and explicit `STATIC_CANDIDATE_ONLY` / `runtime_proven=false` / `uplift_accepted=false` flags. No source coordinates, command payloads, inventories, UUIDs, signs, world NBT, or third-party raw files are included. An unknown family is retained as UNKNOWN. An unfamiliar/malformed schema fails closed. This first cut groups connected physical adjacency, **not** disjoint logical circuits, scoreboard graph joins or actually observed gameplay.

The candidate catalog's aggregate family counts are **not** evidence that a circuit has a Boolean function, logic equivalence, signal timing, conduction, or stateful game mechanic. The original-world and target-version runtime experiments must independently prove these.

## Parallel work cells (bounded, no shared-writer conflict)

| Cell | Producer | Deliverable | Independent evidence / gate |
| --- | --- | --- | --- |
| R1 legacy static motifs | #34 + source-only tool in this PR | Discovery-only CORE motif signatures, sample classification and first unknowns | Original 1.8.8 graph must be available via an admitted location; no third-party upload |
| R2 contemporary hybrid graph | #34 | Compare Sprint Racer modern physical census + programmable graph; identify cross-format evidence join and gaps | Provenance/license boundary preserved; do not equate file counts with interactions |
| R3 precise domain semantics | #27 + mc-reversing-lab #253 | Targeted physical sensor, electrical, inventory and command state contracts | Exact release + existing independent oracles; no code duplication |
| R4 differential / adversarial | #11 | Inject sensor/input/time/inventory variations; capture state transitions, first failure and negative controls | Real isolated original-epoch game; then separately native 26.3 |
| R5 uplift recipe | #35 | Evidence-bounded legacy->26.3 implementation and exact observable contract | Static schema validation and official 26.3 player/runtime equivalence; no blanket modernization |
| Forward consumer (independent) | MCSTORY/MCWORLD #17/#19 | Select accepted mechanism via capability resolver for one story objective | No dependency on R1–R5 completion unless slice explicitly consumes a capability |

## Immediate acceptance questions

1. Are aggregate grouping output and hard negatives deterministic and privacy/copyright safe?
2. Can the 403 CORE cross-domain *adjacency* components be reduced to a useful candidate shortlist without pretending connectivity implies causality?
3. Can one representative mixed candidate be reconstituted as a safe synthetic fixture that matches a preexisting exact-version runtime oracle? **Do not copy restricted world content.**
4. Can a first recovered contract be expressed as input/state/transition/output/reset/persistence/time/observation, with UNKNOWN where not proven?
5. Does that contract enable a different or cheaper realization for Lantern or a Barsoom named place, or should it remain knowledge only?

## Serialization / safety controls

- The new source-only R1 tool is not a replacement for the existing CORE analyzer, Redstone matcher, catalog writer or world generator.
- Use a *separate isolated branch* rooted at pinned public PR #12 head; do not mutate #12's own branch, existing accepted matchers, or private forward-story code.
- **Do not dispatch** the deferred Sidecar #381, consume private Actions minutes, run a paid executor, merge, change production or touch any existing save.
- Phase-A acceptance-ready evidence is not Phase-B cross-domain admission. Restrict changes to discovery and synthetic hard-negative tests until the existing project authority explicitly admits the required cross-domain test.
- Do not evade any previous safety-refused source write; those remain held on their original target and branch.
- No copyrighted raw third-party worlds or game source in public CI artifacts.
- Record each first failure and exact-head verification in #34; #27 owns causal semantics, #35 owns uplift; #19 stays forward consumer.

## Next cold-start baton

Discover current source head and PR exact base; run 10 synthetic tests; independently validate derived-only output and negative controls; on *permitted* existing CORE graph obtain first signature distribution, keeping physical grouping vs dynamic semantics separate. Then select one bounded candidate for a genuinely original-epoch behavioral qualification. Do not promote any recovered gameplay primitive until independently accepted by the owning source/runtime DLE.
