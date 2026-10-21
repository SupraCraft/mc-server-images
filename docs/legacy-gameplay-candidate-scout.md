# Legacy gameplay candidate scout — bounded static discovery

This candidate supplements, not replaces, the existing `tools/analyze_legacy_causal_machinery.py` output on the same exact source branch. It **does not** read copyrighted world archives or infer gameplay from physical proximity alone.

```bash
python tools/analyze_legacy_causal_machinery.py --world-zip <private-local-input.zip> --output <private-local-graph.json>
python tools/scout_legacy_gameplay_mechanisms.py --graph <private-local-graph.json> --version 1.8.8 --output <new-derived-report.json>
python -m unittest -v tests.test_scout_legacy_gameplay_mechanisms
```

The first invocation may only be performed where intake rights, native world version and source custody are satisfied. Do not upload the source world, raw graph, command strings or coordinates to public Actions. The scout exports **aggregate derived-only** family counts and candidate types and deliberately labels every result `STATIC_CANDIDATE_ONLY`.

Three experimental motifs are currently identified as directed **hypotheses**: sensor→dust→command; sensor→dust→actuator; dust→command with authored world target. Each requires an actual exact-original-version stimulated-world observation before it becomes a semantic fact. Single physical adjacency, unsupported source version, malformed pointers or duplicate node identities cannot establish any candidate.

No exact-version native test, behavioral equivalence, client experience or 26.3 uplift is claimed here. The independent code reviewer should check edge-domain assumptions and materialized readback before selecting a runtime canary.

DLE: [Corpus #34](https://github.com/SupraCraft/mc-server-images/issues/34), [Causal #27](https://github.com/SupraCraft/mc-server-images/issues/27), [Uplift #35](https://github.com/SupraCraft/mc-server-images/issues/35).
