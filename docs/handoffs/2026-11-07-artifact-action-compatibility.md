# Legacy artifact-action compatibility batch

Base: PR112, source17f45ad. Eleven mutable upload-artifact v4 uses now pin
Node24 action `cf430e030ddbb5b0abf93d22962f4752f3646cd9` with explicit
`archive: true` to retain ZIP archive behavior. Names, paths, retention,
missing-file handling and `if: always()` failure-custody conditions remain.

Fetched immutable action manifests: old Git blob
`2a0ecf19e8d0087dd2e5d1785dcf764811e79fae`, new Git blob
`7cb4d1e81db55320b41217e1a78a1a46e3d2baef`. Compared compression-level,
include-hidden-files, overwrite, retention-days and if-no-files-found defaults:
all unchanged. All supplied input names are supported by the new manifest.
This establishes static input/default compatibility, not uploaded byte parity.

These older probe uploads retain compact reports; existing runtime-lane and
Mojang cross-job download consumers remain untouched by this batch. Real hosted
upload/download, retention and API digest behavior still require admitted CI.
All37 workflows pass actionlint with shellcheck disabled; diff checks pass.

Publication is draft, stacked on112 and marked [skip ci] to conserve reported
exhausted allowance. Remaining: mutable checkout/java refs, independent source
reviews, hosted checks and full managed release smoke. Do not merge based on
skipped checks or source-only artifact compatibility.
