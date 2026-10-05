# World-feature visual presentation standard

Status: candidate minimum presentation contract
Target: named places and qualified architecture/structure exemplars
Minecraft target: Java 26.3+

This standard is presentation evidence. It does not replace semantic/runtime
oracles or stock-client human acceptance.

## Applies to

Every visually qualified subject must declare its class:

- `named_place` — singular world/story identity;
- `structure_exemplar` — representative gameplay-structure realization;
- `architecture_exemplar` — reusable physical architecture with no required
  gameplay-structure semantics.

The same presentation machinery may be reused across all three classes. The
receipt must not imply place identity for a reusable structure or architecture
exemplar.

## Minimum evidence package

### 1. Static review set

At minimum:
- approach;
- exterior three-quarter;
- interior/use-space when the subject has an interior;
- recognition-cue detail;
- landmark/distance or contextual view;
- terrain/site-fit view when terrain matters.

### 2. Grounded proof walk

A short bounded traversal captured from the actual grounded client actor.

Default:
- 12 fps;
- approximately 8–12 seconds when the route supports it;
- no viewer-only displacement counted as traversal;
- receipt records start/end, distance, duration, frame count and authority.

This is continuous traversal evidence.

### 3. Real-estate walkthrough

A smooth reviewer-facing tour covering the subject as if inspecting a property
or physical site.

Default:
- 15 fps;
- approximately 20–30 seconds;
- exterior approach/reveal;
- side or yard/context pass;
- doorway/threshold transition where relevant;
- interior circulation;
- required recognition-cue closeups;
- rear/alternate exterior;
- elevated fly-over or orbit.

Viewer-only camera motion is allowed but must be marked
`presentation_only`.

### 4. Continuous loop GIF

A compact visual summary suitable for rapid issue/review scanning.

Default:
- 10–12 fps;
- 6–10 seconds;
- closed camera orbit preferred;
- first frame is not duplicated at the end;
- infinite loop;
- palette optimized;
- presentation-only authority.

## Artifact names

Use subject-slug prefixes:

- `<subject>-proof-walk.mp4`
- `<subject>-realestate-walkthrough.mp4`
- `<subject>-realestate-loop.gif`

A compatibility alias may be retained temporarily when replacing an older
artifact name.

## Authority boundary

Visual presentation and semantic qualification are intentionally distinct.

- grounded proof walk: traversal evidence;
- viewer-only walkthrough/fly-over/GIF: presentation evidence;
- structure capability or construction receipts: gameplay-semantic evidence;
- stock vanilla-client HIL: final visual acceptance where required.

Cinematic quality must never manufacture semantic authority.

## Retention

Keep in Git only review-sized durable evidence:
- selected stills;
- compact MP4/GIF when reasonably sized;
- route metadata;
- receipts/reviews.

Keep heavy/raw material in expiring Actions artifacts:
- raw frame sequences;
- packaged world ZIP;
- other transient generated inputs.

If media grows enough to impose repository cost, prefer the Actions artifact and
retain a compact durable receipt with hashes/coordinates rather than weakening
the evidence contract.

## Generalization rule

A subject-specific route is data. The capture/encoding engine is shared.

Do not fork a new visual workflow per place or structure. Add new camera paths,
recognition cues and subject metadata to route data; change the engine only when
a genuinely new presentation primitive is required.

## Failure policy

Fail closed when:
- required frame sets are absent;
- frame count is below the configured minimum;
- MP4/GIF encoding produces an empty artifact;
- exact-version renderer/server preconditions fail;
- grounded traversal falls below its declared route oracle.

A failure in a presentation-only cinematic segment must not be silently
reclassified as a semantic failure; receipts should preserve the failure domain.
