# Local qualification corrections, 2026-11-07

Status: local candidate source and offline verification only. Owning DLE:
[Server Images #53](https://github.com/SupraCraft/mc-server-images/issues/53).
Re-read live authority before publication or hosted execution.

## Diagnosis and corrective plan

Baseline `0e9033031d16010ca4b69589c778d6de8152261f` ran 87 tests:
Windows Python 3.12.10 reported six failures and eight errors; local Ubuntu
24.04 / Python 3.12.3 passed all 87. Five failures expected Linux secure
descriptor reads on Windows, eight errors required unavailable symlink
privileges, and one assertion hardcoded POSIX path separators.

1. Preserve production fail-closed filesystem guards. An unsupported secure
   reader must refuse before opening region data or invoking its decoder.
2. Probe required capabilities in tests. Skip only dependent fixtures; retain
   portable malformed-archive, region-bound, staging and invalid-release checks
   as separate tests. Test that unrelated filesystem errors still propagate.
3. Compare world-agent paths using native path semantics, preserving the
   trailing separator required by its allowlist contract.
4. Verify the combined source candidates on Windows and Linux, then retain
   scoped commits for separate integration and hosted-run admission.

No production world/security logic changed in the portability corrections.
The combined branch also contains the previously verified two-workflow Node24
pin migration and Mojang dispatch/publication fix. These remain independent
commits, originating at `97406c874a444093c7ffbdc20be0a8128aa78d38` and
`5f5c36816be2791b2cf65def095470e94e6a4644` respectively.

## Verification and reproduction

From a native checkout with Python 3.12:

```text
python -B -m unittest discover -s tests -v
python -B tools/validate_minecraft_hosting_stack.py
python -B tools/validate_world_activation_transaction.py
```

Combined candidate at `acec0ad`: Linux **100 passed, zero skips**; Windows
**85 passed, 15 explicit capability skips**, zero failures/errors. The skipped
cases cover seven secure-reader/link cases, four world-agent link cases,
two region/archive link cases and two actual link-capability probes.
Linux exercises all of them. Synthetic failure-receipt tests intentionally
print a FAIL classification; unittest's terminal verdict is authoritative.

Windows-created Git worktrees contain Windows-form gitdir pointers, which
Linux Git cannot resolve. A first WSL run against such a worktree failed the
exporter's exact-source-commit lookup. Reproduced the combined branch in a
temporary native Linux clone instead: all 100 tests passed, including source
identity. Remove the disposable clone after verification; do not rewrite
shared Git metadata to accommodate a second OS.

Actionlint 1.7.12 passed the three changed workflows with shellcheck disabled
(unavailable). This is static validation, not hosted action/artifact behavior.
Local Mojang publication tests use only a disposable bare Git remote.

## Remaining gates

Independent source integration and separately admitted hosted action/artifact
verification remain open. Remaining Node20 pin migrations, timeout/concurrency
triage and native gameplay/identity/client qualifications remain separate
worksets. Local test success grants no publication, merge, release, runtime
acceptance or physical APPLY authority. Keep main unchanged and clean; retain
candidate branches and remove clean temporary worktrees after reconciliation.
