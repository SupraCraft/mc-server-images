# setup-python compatibility batch

Base: PR #110, source `263911f0eb2455c20c5d055892ee64520f04f40a`.
All 17 setup-python v5/v6 uses now pin
`ece7cb06caefa5fff74198d8649806c4678c61a1`.
Seven v5 uses change action runtime from Node20 to Node24; ten v6 uses gain
immutable source identity. Python-version inputs, commands and permissions
are preserved. No selected step enables action-managed package caching.

Fetched upstream action manifests: original v5 action Git blob
`efa8de904209196588db1453bdb44079b3c393d7`; selected v6 action Git blob
`7a9a7b634ec348b35b882f1f14fcaa4d41836a8e`. All selected input names exist
in the new manifest; the interpreter version remains a separate explicit
workflow input. This is static compatibility evidence only.

All workflow changes are exact ref substitutions. YAML and actionlint checks
cover syntax; hosted Node24 execution, tool-cache acquisition and artifact
consumers remain unearned until admitted CI. Publication uses `[skip ci]`
under the owner's reported allowance constraint. Keep this PR draft and
stacked on #110 for independent review; do not merge around pending checks.

Remaining action work: setup-node upgrade/cache-default review, legacy
upload-artifact v4 archive compatibility, mutable checkout/java refs.
