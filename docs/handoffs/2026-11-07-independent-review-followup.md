# Independent review follow-up

Review of the source stack identified a CI coverage gap: no existing workflow
executed the new Mojang-publication or filesystem-capability regression suites.
Mentioning a test in a paths filter did not execute it. The new bounded
source-safety-regressions workflow invokes both suites explicitly, using
read-only permissions and immutable actions. It launches no game server or
Mojang download and publishes no evidence branch. Its Git operations are
against disposable local fixture repositories only.

Local Ubuntu24.04 verification: publication suite3/3 pass, capability suite5/5
pass, zero skips. All38 workflows pass actionlint with shellcheck disabled.
Hosted invocation remains unearned at the skipped draft head.

The independent reviewer reported no production blocking flaw in inspected
Mojang event/token/head-lease handling or runtime policy fields. The review
ended at its execution usage limit before a complete terminal report, so it
is partial review, not an approval or exhaustive clean bill of health.
Remaining source review and hosted checks precede merge and runtime smoke.
