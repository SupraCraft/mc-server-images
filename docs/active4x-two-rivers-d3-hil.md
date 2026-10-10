# Two Rivers D3 — stock-client HIL

This is the first gate that intentionally requires a human using the **unmodified
Minecraft Java 26.3 client**. All setup, caravan dispatch, restart, evidence
collection and scoring are automated.

From a checkout of `SupraCraft/mc-server-images` on
`feat/named-place-visual-qualification-v1`, run:

```powershell
py tools/run_active4x_two_rivers_d3_hil.py
```

The harness builds an isolated Docker Compose project, starts the pinned
exact-26.3 server/director/actor stack, and tells you when to join
`127.0.0.1:25585`.

The only required human work is ordinary gameplay:

1. Near spawn, move **2 wheat** from the starter barrel at x=-8 into slot 1 of
   the trade-input barrel at x=-6. The trade output appears at x=-4.
2. Move **4 bricks** from the starter barrel into slot 1 of the build-supply
   barrel at x=0.
3. Break the red-concrete obstruction marker at x=2,z=16.
4. Break the cobblestone damage marker at x=6,z=16.
5. Stay nearby long enough to observe the autonomous caravan.
6. When the game tells you phase 1 is complete, disconnect. The harness restarts
   the server. Reconnect when the terminal tells you to.

No operator/admin Minecraft commands, evidence copy/paste, or manual scoring are
required. The harness writes
`probes/active4x/two-rivers-d3-hil-result.local.json`.

The optional two-simultaneous-human rep is deliberately not required for first
D3 promotion.


For the lowest-toil evidence path on a clean feature-branch checkout, use:

```powershell
.\tools\Start-TwoRiversD3Hil.ps1 -Publish
```

The PowerShell launcher verifies the required clean feature branch, fetches and
fast-forwards safely to the current remote revision, and refuses to reset or
overwrite uncommitted work. The HIL harness checks actual command exit status
for server/director/actor readiness before accepting gameplay. Docker and
Python 3 must already be available, and the stock 26.3 client is still operated
by a human.

On PASS, `-Publish` commits and pushes only the canonical HIL receipt
(`probes/active4x/two-rivers-d3-hil-result.json`). It refuses to publish if the
checkout has unrelated changes, so it will not silently sweep other work into
the evidence commit.


At the end, the harness asks one grouped yes/no HIL question confirming that
the trade output, build change, obstruction/damage consequences, and caravan
were actually visible/understandable. This is the only qualitative human
attestation; automated receipts are not used as a substitute for legibility.
