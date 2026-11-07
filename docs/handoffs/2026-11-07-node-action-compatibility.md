# setup-node compatibility batch

Base: PR #111, source `6afdf19`. All 19 setup-node v4 or equivalent pinned
uses now select immutable v6 commit `249970729cb0ef3589644e2896645e5dc5ba9c38`.
Upstream action manifest Git blob `79813721449fefd25fbf7008327b5d59735eeb89`
declares Node24 and automatic package-manager caching enabled by default.

Every selected old step supplied only node-version and no cache input.
The replacement adds `package-manager-cache: false` explicitly, preserving
the absence of automatic caching. Existing Node22/Node24 interpreter choices,
commands, tokens, permissions and workflow events are preserved. Action
runtime version and installed product Node version remain distinct.

Parsed all selected steps and verified input scope before mutation. All37
workflows pass actionlint1.7.12 with shellcheck unavailable/disabled; diff
check passes. Hosted Node acquisition, runtime and cache behavior remain
pending; no Docker/local act execution is claimed. Draft publication is
stacked on #111 with [skip ci] under the reported allowance constraint.

Remaining: legacy upload-artifact archive compatibility, mutable checkout/java
refs, independent review of stacked PRs and admitted hosted checks. Full
managed release smoke and identity/client qualifications remain separate.
