# Main integration and release-smoke prerequisites

PR115 integrated the complete reviewed stack atomically at main
`197a203e1658498d534bd33632fc013d2bb4e50a`. Its tree equals reviewed
head24fc90f; the final publication-race fix was never omitted from main.
PR110 is included; PR111–114 are superseded and closed.

Post-merge public run42393293779 PASS: offline job128465212876 and action
job128465248998. The scope is101 offline tests, contract/RCON checks,
Python/Node22/Java25 actions and tiny archived artifact upload/download.
It does not start Minecraft or qualify release integration.

The next gate is managed release smoke. Prerequisite reconciliation found
later native evidence omitted by the recent policy update: Agent Dispatch
PR545 merged to experiment source8744304c3c0a332460b1c5db97a2fb1e9562b222;
public run40119184140 and native job120947794366 succeed. Live logs show
target25.04.2.6 and SUPPORTED/oracleSatisfied:true. The owning native DLE
historically accepts OP4P-023/catalog1.15.33 with lifecycle, provider readback,
staging, fault rollback, synthetic client/backend checks and cleanup.
The Actions artifact API now lists no archives for that run; detailed raw
artifact bytes were not independently re-downloaded in this reconciliation.
Preserve the distinction between historical scoped acceptance and fresh
byte-level evidence. OP4P-023 is consumed: never replay it.

Still required for managed release: current intended assembly/source pins,
independently admitted account/VIP/realm authorization, managed deployment
mutation and rollback, full Two Rivers/Gym gameplay, stock-client qualification,
and complete cleanup receipts. Use existing identity/COLLAGE/Foundry/Gym
owners; do not invent new credentials, managers or claim acceptance from
source-only receipts. Physical APPLY stays HOLD. Update these owners before
any new heavyweight experiment; do not rerun a qualified historical lane
merely to obtain another green workflow.
