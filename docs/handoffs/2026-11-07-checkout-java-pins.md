# Remaining action tag pinning

Base: PR113 at `d0011bdddc2a1e27947c130fa319f2a7cfd67d67`.
Fifteen checkout v5 tags now pin their currently resolved immutable source
`fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09`; thirteen setup-java v5 tags pin
`b6effb05e454b25005698d916606bdc6ffcbf961`.

Upstream manifests independently fetched at those commits declare Node24:
checkout manifest blob `5b0524f730db83f9513c18ab31a6c086c7239076`, setup-java
manifest blob `396e53c708fa14eaf6f45eaa50e8ae499c1aa498`.
These freeze the same major-tag targets observed during this batch; there is
no action major migration. Existing inputs, credential settings, Java versions,
commands, events and permissions are byte-preserved outside ref replacement.
Reverse substitution reproduced every original changed file exactly.

All37 workflows pass actionlint1.7.12 with shellcheck disabled. No mutable
first-party action tags remain in the combined candidate. Hosted execution
is still unearned and intentionally skipped at this draft publication head.
The historical source audit records its own earlier source commit; it must
not be interpreted as a census of this successor branch.

Next in order: independent source review, admitted hosted source checks, then
distinct justified runtime/artifact checks and the managed release smoke.
Pending checks must be earned before merge; physical APPLY remains held.
