# Prismarine Viewer local 26.3 build

This directory carries a **small patch queue against an exact upstream commit**.
It is not a fork of Prismarine Viewer.

## Upstream baseline

- repository: `PrismarineJS/prismarine-viewer`
- commit: `7fa43a7317467a3ba84f857ba6b1ca9597c72b8c`
- upstream CI style: Node 24, StandardJS lint, generated render assets, version-scoped Jest rendering tests

The baseline SHA is intentionally pinned. Updating it is a separate reconciliation
change and must be followed by patch re-application and qualification.

## Patch policy

Each file is one reviewable concern and must:

1. apply cleanly with `git apply --check`;
2. follow upstream StandardJS conventions;
3. avoid SupraCraft-specific APIs inside upstream source;
4. include a narrow reason and deletion condition;
5. be independently removable when upstream supersedes it;
6. preserve exact-version provenance.

Current patch:

- `0001-local-26.3-use-26.1-render-assets.patch`
  - **status:** local diagnostic bridge only;
  - **purpose:** allow an exact-26.3 world/client to be rendered using the
    closest currently generated 26.x viewer assets;
  - **not an upstream support claim;**
  - delete when exact 26.3 viewer assets are generated and qualified.

## Build contract

`tools/install_prismarine_viewer_local_26_3.sh`:

1. clones the exact upstream SHA into a disposable directory;
2. applies this patch queue;
3. runs upstream `npm install` so `prepare` regenerates viewer assets;
4. runs `npm run lint`;
5. verifies generated 26.1 texture/blockstate artifacts;
6. exposes the locally built package through a disposable `node_modules`
   projection.

No Prismarine repository is forked, no upstream branch is mutated, and no
generated Mojang asset corpus is committed to SupraCraft.

## Promotion rule

A patch is an upstream candidate only after its behavior is:

- generic to Prismarine rather than SupraCraft;
- covered by the smallest upstream-style regression test possible;
- qualified against the exact affected Minecraft version;
- free of local paths, harness assumptions, or policy logic.

The named-place walk-through, screenshot-review policy, and MCWORLD acceptance
logic remain SupraCraft responsibilities and should not be proposed upstream.
