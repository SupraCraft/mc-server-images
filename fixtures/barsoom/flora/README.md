# Barsoom Flora v0 — vanilla Java 26.3 public-safe native fixture

**Authority:** [SupraCraft/mc-structure-foundry-private#46](https://github.com/SupraCraft/mc-structure-foundry-private/issues/46), under MCWORLD #17.
**Runtime:** Official Java 26.3 / Java 25; datapack format [121,0]; no mod/plugin/client resource pack. Existing Barsoom v0.2 terrain/outpost remain unchanged.

## What this does (and does not do)

Five separate flora proxies are implemented with ordinary vanilla blocks:
- `scarlet_underbrush`: crimson roots on crimson nylium (decorative grass).
- `thorn_shrub`: mature sweet berry bush on dirt (native contact hazard/berries).
- `canopy_tree`: warped stem and warped wart canopy (static alien tree).
- `canal_crop`: hydrated farmland, nearby water and mature wheat (native harvest).
- `predator_fungus`: crimson fungus with a separate marker-based poison radius, evaluated once per second (bounded scripted carnivore proxy).

This DOES NOT register new plant blocks, retexture them, change world biomes, simulate tree growth/seasonal ecology, or create a new AI. The carnivore appearance remains a vanilla fungus. Species names describe the *prototype design intent*, not an already customized visual asset. No custom plant is automatically added to world generation.

## Safe demonstration

The `barsoom_flora:demo` function alters blocks at **five sites** relative to the command source. **Do not run it on an established save** or an occupied area: use a new disposable world and a dedicated staging region.

Build:
```bash
python3 fixtures/barsoom/flora/gen_flora_263.py --output /tmp/barsoom-flora.zip
```

Stage the ZIP in the fresh world `datapacks/` and enable the pack before startup (the native harness does this automatically). On an operator console of a disposable world:
```text
execute positioned 520 192 520 run function barsoom_flora:demo
```

The five specimens are arranged along X offsets -8, -4, 0, 5, and 9 at Y 192, Z 520. The isolated demo is intentionally not automatically activated on pack load. `#minecraft:load` schedules only a lightweight, once-per-second hazard evaluator capped to 8 marked plant anchors; there is no per-tick worldwide plant scan. A repeat of the demo does not create a duplicate carnivore marker within the same site.

## Tests / evidence discipline

```bash
python3 tests/test_barsoom_flora_263.py
python3 tools/qualify_barsoom_flora_263.py --evidence probes/26.3-release-identity.json --out /tmp/flora-native.json
```

The native test requires Java 25, the official server download, and a disposable loopback-only world. It checks exact version, pack load, all five plant block witnesses, real native command execution, marker presence, duplicate marker prevention, save/stop/restart, and persisted plant/marker observations. The generated receipt distinguishes PASS from HIL and ecology behaviors that have NOT_RUN/NOT_IMPLEMENTED.

The public standard GitHub-hosted workflow carries the runtime test; do not schedule this on private-repo GitHub Actions minutes.

## Next experimental steps (separate gates)

1. Prove actual player proximity damage/recovery and berry/crop gameplay using pinned synthetic 26.3 client transport; check no unintended harm outside the radius.
2. Compose the flora pack with **immutable** qualified Dead Sea worldgen/outpost v0.2 source in a new disposable world and re-run the accepted original quest oracles (not new replacements).
3. Add stock-client visual review and original resource-pack artwork, without confusing a shared vanilla block texture with a novel registered species.
4. Implement biome-aware deterministic natural placement, tree/sapling growth and water/climate-conditioned crop cycles through MCWORLD's worldgen compiler (not the display-only fixture).
5. Profile bounded 8-anchor rep, then design scale/admission controls before anything exceeds the canary.

**Production world / physical TrueNAS APPLY: HOLD.** Never merge draft PR on static-only evidence.
