# CORE v1.4 — Four-channel clickable-chat / Redstone state controller source disassembly

**Date:** 2026-10-26 (Europe/Berlin). **Scope:** original Minecraft Java 1.8.8 `CORE v1.4` world by **UnlikelyWaffle**, **CC-BY-SA-4.0**. This is a reproducible read-only **source-level program disassembly**; it is *not* an authorized original Java runtime, a native gameplay behavior claim or a Minecraft 26.3 uplift. Owning [DLE #34](https://github.com/SupraCraft/mc-server-images/issues/34).

**Original exact pins:** ZIP `sha256:61092508c78f5dbe36b03a9d0bdb202c5ddfe71f1aada58d62ae81ae93f5a998`; existing recovered complete source graph `sha256:5a5c25a31e2bcdec1f2d7d18cc4dedfc87c5a43e53cab4529e5bcdac0452efb5`. The creator's online listing later reports **v1.4.1**. The recorded creator/player statements and their later release cannot be treated as proof that each scene exists unchanged in pinned v1.4.

## What was implemented and qualified

[`tools/trace_legacy_core_ui_controls.py`](../tools/trace_legacy_core_ui_controls.py) is a bounded read-only layer over the existing fully SHA-qualified 1,445-command original program and [`tools/reconstruct_legacy_core_command_controls.py`](../tools/reconstruct_legacy_core_command_controls.py). It recomputes the clicked `tellraw` `run_command setblock` target points **inside** the existing ephemeral and hash-pinned source-custody workcell, requires the exact original physical-command adjacency and diode metadata/graph edges, follows only independently oriented rear/front diode joins (up to 32 stages per candidate), accepts strict typed wire continuation only where recorded, and parses aggregate downstream terminal command semantics.

Source identities/coordinates, raw JSON, message content, original command bodies/hashes, actor names, per-lane addressable circuit details and source world archives are **not emitted**. Only aggregate source classes and nonpromotion flags are permitted as artifacts. The original world and graph remain immutable.

### Recovered source-authored program skeleton

```text
Player-facing tellraw JSON [13 command-bearing click events]
   → /setblock <one of 4 original absolute targets> redstone_block
   ├→ exact adjacent original command block
   │    ├→ setblock same target AIR (possible local reset)
   │    └→ tellraw player feedback
   └→ correctly faced 1.8.8 repeater rear input
        → serial, collinear original repeater direction chain
        → final original command block
             ├→ tellraw (three chain endings; one contains clickable events)
             └→ tp entity-selector with relative-coordinate argument (one chain)
```

This is **potential source dataflow/control geometry**. Nothing establishes that the player could successfully click in a given mode, that any input caused a powered edge, that the reset writer actually succeeded, that the target entity matched Blaze, or that author-intended gameplay completed.

### Verified counts from the pinned original

| Source-backed observation | Value | Evidence strength |
|---|---:|---|
| Original authored command blocks completely SHA verified | 1,445/1,445 | Exact source data |
| Distinct absolute clicked Redstone target points | 4 | Exact original author instruction arguments |
| Click actions specifying Redstone block placement | 13 | Authored JSON click controls, no executed clicks |
| Targets with adjacent command port + aligned diode rear input | 4/4 | Static typed original geometry |
| Targets with separate original authored AIR writer | 4/4 | Exact same-world target, possible reset |
| Immediate direct-source candidate operations | 4 `setblock`, 4 `tellraw` | Adjacent original command texts |
| Original serial repeater nodes inspected | 52 | Saved source graph + historical facing |
| Exact serial repeater-to-repeater geometric port joins | 48 | Historical facing and original oriented edge |
| Exact front repeater to terminal command port joins | 4 | Original oriented edge |
| Saved repeater delay setting | **4 Redstone ticks** for all **52** | Original 1.8 metadata, not timed observation |
| Per clicked-target chain stage histogram | **9 stages (2), 16 (1), 18 (1)** | Source geometry per target, aggregate only |
| Per clicked-target cumulative configured delay | **36 Redstone ticks (2), 64 (1), 72 (1)** | Source sum, not runtime |
| Distinct terminal instruction families | 3 `tellraw`, 1 `tp` | SHA matched original command verbs |
| Terminal `tellraw` containing another click event | 1 | Authored JSON (not clicked) |
| Other terminal `tellraw` messages lacking click events | 2 | Source parse |
| Terminal `tp` target class | Entity selector, relative operand present | Original syntax only, entity binding unresolved |

At an ideal 20 game ticks/second a Redstone tick represents ~0.1 seconds, yielding **3.6s** (two source paths), **6.4s**, and **7.2s** *nominal configured repeater sums*. **Do not misreport the overall 52 repeaters as four equal 13-stage/5.2-second chains.** The per-target histogram independently falsified that earlier equal-size conjecture. These values do not measure tick order, repeater locking, comparator behavior, actual signal propagation, server lag, or player experience.

### Creator external oracle and open questions

The [original creator discussion](https://www.minecraftforum.net/forums/mapping-and-modding-java-edition/maps/2432763-core-puzzle-adventure-map?page=3) describes a Blaze possession scene with clickable JSON chat controls and time-dependent entity interaction. The reconstructed **four-channel clickable + timed Redstone + terminal `tp @e...`** circuit is compatible with such an interface but **not yet proven to implement the Blaze mechanic**. The original terminal `tp` has an **entity selector** but the bounded source parser does **not** establish its actual actor type, target binding, permissions, or scene context. The presence of twelve independent original `summon Blaze` author instructions elsewhere in the world is not an exact causal join.

Other original creator-confirmed gameplay oracles remain: Dr. H dialogue → Redstone clock → entity presence/death → skull → ending branch; chess pieces (armor stands/skulls) and particle hint; item-drop inventory conversion; clock and chest puzzle; two-piston/lamp objective; environmental maze; self-repair and good/bad replay. See [external evidence index](legacy-core-author-player-walkthrough-evidence-20261025.md). Do not silently generalize this four-channel pattern to those unrelated scenes.

### First failures and corrective actions

- **F-107-UI-TRACE-008:** original downstream-only static trace recovered `4 setblock + 4 tellraw` but incorrectly left all diode-front components as UNKNOWN. Added source-oriented diode-front check; pinned scan proved four other front components were legacy repeaters, **not actors**.
- Extended the tracer across exact historical repeater output→next repeater rear orientations, with a bounded worklist, explicit graph-edge admission, cycle cutoff and separate handling of weaker typed dust possibilities. The next original run discovered **48** aligned serial repeats and four terminal original commands.
- A subtle harness bug reused a `visited` variable for dust and diodes; corrected separate visit sets. New missing-delay metadata expected in old synthetic fixtures caused a short-lived source-free test failure; corrected fixture to assert explicit UNKNOWN metadata rather than falsely manufacture timing.
- **F-107-UI-TIMING-009:** initial shorthand incorrectly inferred four equal 13-repeater paths from the **aggregate 52**. Corrected by auditing **each target's original stage count and saved delay privately**, emitting only a safe multiset histogram: **2×9, 1×16, 1×18**. This does *not* reveal raw source locations or exact player-facing strings.
- Historic creator / player reports are external, possibly v1.4.1 and not executed original v1.4 proof; source uncertainty preserved rather than falsely admitting gameplay.

### Exact evidence / verification

1. [Synthetic public free-tier GitHub Actions **40244528745**](https://github.com/SupraCraft/mc-server-images/actions/runs/40244528745), exact suite head **656549db9ebce48750f11507d1377d09f8cdafbe**: **235/235** synthetic tests PASS. Includes full legacy source-hash/custody controls, forged links, wrong-facing rear input, missing original AIR writer, missing `clickEvent`, dynamically player-relative `~`, bounded serial/dust paths, saved delay metadata, duplicate action counting, entity selector privacy, no semantic promotion.
2. [Pinned original source-only public/free **40244546305**](https://github.com/SupraCraft/mc-server-images/actions/runs/40244546305), exact executable HEAD **5edc3d35530a90db7d845eb8cda2d63f81eea530**, job **121323235663**, **COMPLETED/SUCCESS**. Reconstructed the original immutable source graph with strict pin hashes; both new aggregate file and all existing source-custody/nonpromotion guards PASS. Attributed derived artifact **12617649454**, archive digest **sha256:63a8b74e5453bb8cd057a41583dc8e2861ef81539f1b869ec2055c6cfc281e**, expires **2026-11-08 23:24:10 UTC**. No raw original, exact source identities or map transfer.
3. Existing 10-source-channel CORE survey, original mechanics archive/graph and creator/player historical oracles remain intact and unchanged. No native Java execution was initiated.

### Next READY executable, source-only

**First priority:** disambiguate the original terminal `tp` selector *inside* existing source custody by source-only parsing of selector type and any exact command-side entity signature, plus original UI click-control reuse. Attempt an exact source-supported comparison to authored Blaze possession scene: actual actor summon/effect/subject control and the world/dataflow to one of the four controller targets. **If exact joins absent, mark `BLAZE_CONTROL_SCENE_UNRESOLVED`**, not a gameplay fact. Avoid printing command argument/selector/coordinate.

**Parallel independent work:** bounded Dr. H end dialogue→clock→presence/death→skull→ending source slices, and chess armor-stand/skull hint/particle inventory evidence. Only accept exact historical predicates, typed current graph relations and creator claims as *separate evidence classes*. Admit nothing solely from proximity, similar actor names or forum story. Preserve all 10 channel coverage and unknowns; update source-safe Mechanism IR, first failures and DLE.

**Gates:** PR #107 remains DRAFT/UNMERGED. PR #108 original-native attribution workflow explicit safety refusal remains **STOPPED**, with no alternate runner, account, actor or renamed route. No official Java 1.8.8 player-runtime/native experiment, #27 gameplay semantics acceptance, #35 26.3 port/HIL, merge/release, physical/TrueNAS deployment, private/paid runner or expanded credentials admitted.
