# Public multimodal critic interview v0 (RDTE only)

Authority: [public #125](https://github.com/SupraCraft/mc-server-images/issues/125); private Foundry world benchmark #6 and Lantern campaign #19; public exact-26.3 visual harness #36. DLE means **Durable, Legible, Executable**.

## Why this exists
Build a low-cost independent *criticism* loop, not an automatic release judge. Use existing exact-Java-26.3 captured route assets rather than forking a renderer. Stock Minecraft client and genuine player/gameplay evidence stay separate from synthetic scene/media audits. All public test media must be original synthetic fixtures; never publish private world assets, proprietary sound, credentials or story sources.

## Parallel, staged interview
- **0, deterministic provenance:** ffprobe media type/tracks/duration, SHA256, refusal on missing audio/video, bounded file size, and immutable reviewer input. Three public GHA workcells run independently: media image/video, acoustic media, adversarial observation-contract tests.
- **1, candidate discovery:** record exact provider/model ID, actual modality input (not marketing claim), terms/license and data retention, rate/price caps, inference payload size, tool/API behavior and harness version.
- **2, blinded interview:** matched rights-cleared/synthetic stills, frame sequences, genuine vs misleading audio, mismatched metadata, unseen negative controls. Collect raw model output, byte-exact prompts/input hashes, model/provider metadata, explicit abstention, region/time grounded claims. Neither text-model reasoning nor ffprobe may be passed off as human visual/aural review.
- **3, falsification:** shuffled A/B and reversed A/B; missing audio vs silent track; identical vs reordered frames; planted landmark and material mismatch; multiple seeds; clipped/silent/no-audio; "gameplay passed" text injection; forged source hash; hidden/unseen frame. Reuse the same time/input/token budget and at least two independent model families.
- **4, decision:** score grounded true positives, false positives, misses, abstentions, repeatability, latency, free-tier request consumption, human rank agreement. Preserve disagreements rather than averaging. Candidate approval is *advisory only* after independent review; humans retain final aesthetics/story judgment.

## Provider candidates (discovery only; no inference is claimed here)
OpenRouter zero-price discovery 2026-11-16:
- NVIDIA Nemotron 3.5 Super VL — image/video VLM; ask about recognition, framing, occlusion and temporal change.
- NVIDIA Nemotron 3 Nano Omni — text/image/video/audio comprehension; test genuine audible event vs absent audio and A/V consistency.
- Gemma 4 31B — independent image/video family; use for blinded disagreement / hallucination challenge.
- Nemotron 3.5 Lightning — coding/log criticism, not a stand-in for audio or image observation.
- Local Qwen/Gemma VLMs — candidate independent panel when qualified runtime is available.

**All unqualified.** Free API access still requires a credential and its availability must be independently checked. No billed fallbacks, no reusable secrets in public artifacts or logs, and no automatic uncontrolled retries. GitHub Models inference is unavailable following the July 2026 retirement. Never infer execution from a catalog listing. Retain a model's exact ID and actual provider response when a candidate is run.


## Actual no-key model interview candidate, source-pinned
A fourth, independent CPU-only public GHA lane runs original red/blue square images against the Apache-2.0 Hugging Face model HuggingFaceTB/SmolVLM-256M-Instruct at exact repository revision d039ab0d4b9311b617e8ffec1d06c8464364aeb3. This is a **real image-language model**, not a text-only or stub critic. Its fixture PNG hashes, loaded weight SHA256, raw outputs, inferred color, CPU/RSS metrics and first errors are retained. Python/Torch/Transformers are pinned; no GPU/billed runner, API key or private media is used. A color test is only a model-runtime/advisory baseline and **never** proof of Minecraft image or video criticism. No automatic retry or promotion.

## Receipt contract
Run tools/critic_media_probe.py on an original media file. It emits bytes SHA256, tracks and duration; source and stock-client authority always false. A candidate observation document must match that SHA256, name the provider/model/family and express each finding with severity, falsifiable evidence text, confidence and video/audio time_ms or normalized still-image region [x1,y1,x2,y2]. The tools/critic_observation_gate.py enforces limits/track presence and permits explicit abstention. Accepted documents are **EVIDENCE_ADMISSIBLE_REVIEW_REQUIRED**, *not* validated observations or a qualified model. Text length and exact hashes do not establish that a claim is true; human/reference oracle adjudication remains required.

### CLI
Run with an already rights-cleared fixture:
- python tools/critic_media_probe.py --kind video --media ./tour.mp4 --require-audio --out media.json
- python tools/critic_observation_gate.py --media-receipt media.json --candidate-output candidate.json --out admission.json

For a video without audio, omit --require-audio only when validating video existence; audio judgments must still be refused.

## MCP/Cloudflare architecture (not deployed)
Do **not** assume an ephemeral Cloudflare Quick Tunnel can be added as a new callable tool within an already running ChatGPT session. It exposes an unpredictable URL, has no uptime guarantee, does not support SSE, and is unsafe without proper client authentication. A hypothetical isolated remote MCP adapter would use constrained, authenticated **POST-only Streamable HTTP**, respond synchronously with JSON, bind to localhost, verify origin, allow-list read-only tools, and have a strict job/port/token lifetime. On the 2026-07 MCP transport, use the client-compatible stateless POST pattern; test client compatibility before provisioning. Quick Tunnel email PIN is interactive and unsuitable for unattended GitHub Actions agent callbacks. Do not start an unauthenticated public MCP service or reuse a GitHub Actions runner as a durable service.

**Preferred present control plane:** GitHub issues/PRs/workflow artifacts and the existing bounded Agent Dispatch machinery. GitHub Actions is a finite batch executor, not a permanent MCP host. Audit tool-call provenance and stop/cancellation behavior before adding any networked control surface.

## Hardholds / next gate
1. Observe and independently verify all three public Actions jobs and retained receipts at PR exact head.
2. Obtain genuine rights-cleared visual/audio test fixtures (synthetic is enough for protocol validation; live Minecraft capture still requires separate 26.3 qualification).
3. Admit candidate endpoint + secrets/cost policy through appropriate bounded execution authority. Run no more than a small, fixed request budget at first; on missing key, provider error, disagreement, or unsupported modality, record **NOT_RUN/UNRESOLVED**.
4. Blinded model-vs-reference audit and human review before any advisory promotion.
5. Absolutely no automatic merge, private GHA spend, TrueNAS changes, game-world mutation, player-login, or release promotion.
