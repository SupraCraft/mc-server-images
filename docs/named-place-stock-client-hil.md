# Named-place stock vanilla-client HIL

Status: future gate after exact-26.3 presentation qualification.

This is the final human-in-the-loop visual authority for a named place. The
Prismarine lane is continuous evidence only and cannot promote a place by
itself.

## Goal

Minimize operator toil: materialize one deterministic packaged world plus a
small review packet so the human only has to open vanilla Minecraft, load the
world, follow the authored route, and record PASS or REVISE.

## Required generated packet

For each named place:

- exact Java version and world data version;
- packaged world fixture built from the same authored place-model revision used
  by continuous qualification;
- source commit/run/artifact identifiers and SHA-256;
- camera bookmarks: approach, after-walk, three-quarter, interior, landmark;
- authored walking route with coordinates and viewing targets;
- expected recognition cues / modifier contract;
- exact-26.3 Prismarine stills and walkthrough for side-by-side comparison;
- a one-page review receipt template.

No Mojang client binaries or asset corpus are retained.

## Human rep

1. Launch an unmodified stock Java 26.3 client.
2. Load the packaged world with the intended graphics/resource-pack profile.
3. Start at the authored approach bookmark.
4. Walk the authored route without creative-flight displacement.
5. Inspect exterior, three-quarter, interior/use-space, and landmark views.
6. Capture screenshots plus one short walkthrough video.
7. Record PASS/REVISE for recognizability, silhouette, palette/material
   language, terrain fit, spatial grammar, scale/compression,
   traversal/readability, and interior/use-space composition.
8. Attach the review receipt and captures to the durable campaign issue.

## Promotion rule

Promotion requires exact-server fixture verification, continuous exact-26.3
traversal/render qualification, independent modifier-oracle PASS, and stock
vanilla-client HIL PASS.

A presentation-adapter defect may be accepted as a documented continuous-gate
capability boundary only when stock-client HIL proves the authored world is
correct. It must not be confused with place-model acceptance.

## Automation frontier

Before asking the operator to run HIL, automate deterministic world export and
ZIP, checksums/provenance, route/bookmark JSON, review-packet generation, and a
preflight that the ZIP loads on an exact 26.3 server.

The operator should not have to reconstruct commands, copy coordinates, or
assemble evidence manually.
