# Two Rivers D4 admission preflight (read-only)

D4 long-running soaks remain **on HOLD** until human stock-client D3 HIL is genuinely completed and the published receipt's provenance is reviewed. Automated D3 rehearsal PASS is necessary but insufficient.

This preflight is pure local file validation; it never launches a Minecraft server, alters a world, installs dependencies, starts a soak, or creates an HIL receipt. It does **not** authenticate a person or verify GitHub provenance. It is preparation, **not** D4 authorization.

From the public feature-branch checkout:

```bash
python3 tools/check_active4x_two_rivers_d4_admission.py
python3 -m unittest discover -s tests -p 'test_active4x_two_rivers_d4_admission.py'
```

Expected at the current checkpoint: `decision=HOLD`, nonzero exit (2), because no stock-client HIL receipt exists. Valid-looking receipts produce `EVIDENCE_READY_FOR_REVIEW`, **not** automatic approval to execute D4.

Owner verification must reconcile the actual stock-client HIL source, qualitative gameplay observation, unmodified exact Java 26.3 player and evidence chain before any D4 run. Do not fabricate this evidence or substitute an automated actor.

D4 will subsequently be staged as one bounded scenario at a time: no-player, passive-player, then intervention-heavy; assert resource conservation, queue/population/actor bounds, monotonically increasing revisions, bounded save growth, deterministic replay and absence of runaway conflict/trade loops. Do not start 24h/72h real-time runs or parallel matrices until short baseline admissions are green. Preserve the vanilla server and no-world-scan scope.
