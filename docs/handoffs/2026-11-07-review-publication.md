# Candidate publication and remaining acceptance

Owner authorized publication for normal source review after release triage.
The branch contains workflow/security corrections, capability-aware tests,
and release policy reconciliation; main remains the deployed source baseline.

The publication commit uses `[skip ci]` to suppress push/pull_request workflows
during the reported exhausted-minute window. GitHub documents this behavior:
https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs
This may leave required checks pending. Draft review is useful now; merge
requires actual required checks after runner admission/capacity returns.

Before execution, re-read the latest owner DLE and runtime tuples. After runner
capacity is available, submit a fresh reviewed head without skip instructions
and qualify source checks first. Run each changed native lane only for a
distinct justified compatibility question, preserving first failures and
cleanup receipts. Do not launch all historical heavyweight lanes together.

Still outstanding: remaining Node20 setup-node/setup-python/upload references,
mutable action compatibility, authenticated identity and realm admission,
current native TrueNAS guest lifecycle, full managed end-to-end smoke and
independent stock-client acceptance. Physical APPLY remains held.

Local `act` assessment remains blocked by the unavailable Docker endpoint.
Do not switch to the physical TrueNAS engine or download runner images as an
implicit fallback. Prefer admitted public GHA when capacity returns.
