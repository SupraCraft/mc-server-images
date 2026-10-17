# Barsoom flora RDTE — native Java 26.3 vertical slice

Authority: SupraCraft/mc-structure-foundry-private#17 (MCWORLD). This stacked
candidate derives from public mc-server-images PR #92, the qualified
barsoom:dead_sea world-preset fixture. No private hosted Actions required.

## Contract

The human-editable species.json is authoritative; gen_flora_263.py creates a
deterministic, five-file optional datapack for vanilla Java 26.3. The catalog
describes five **vanilla proxies**, not new registered Minecraft blocks:

- Red grass: dead bush groundcover on red sand; static visual.
- Thornwood: logs plus persistent cherry leaves; no sapling growth yet.
- Glowcap: crimson fungus, mushroom stalk and shroomlight; static visual.
- Canal reed: sugar cane with water and farmland/wheat; vanilla growth expected,
  but randomized growth rates are not yet qualified.
- Jawbloom: sweet-berry bush and marker; once-per-20-ticks proximity poison
  is scripted for actual players, but player injury is not yet runtime-qualified.

Biome habitat metadata is only a later placement constraint, not a completed
world-generation distribution engine. No new client assets or mod dependency.

## Rebuild and bounded opt-in

Run:

    python3 fixtures/barsoom/flora/gen_flora_263.py --output barsoom-flora.zip --manifest flora-receipt.json
    python3 -m unittest tools/test_barsoom_flora_263.py -v

Stage the optional ZIP into a new disposable 26.3 world datapacks folder
before boot, then invoke as an operator:

    execute positioned 0 160 0 run function barsoom_flora:demo

The demo is intentionally destructive inside 28×13×9 blocks. Never invoke
near player construction or on a valuable save. Loading the pack does not
alter blocks; only a periodic proximity check is scheduled until removed.
No world gamerules, production TrueNAS service or existing saves touched.

## Way of working, native proof and next gates

Discover/Observe: pin the prior immutable worldgen and player acceptance.
Plan: five representative data-defined species with existing vanilla states.
Apply: build independent datapack and opt-in garden function.
Verify static: deterministic ZIP, syntax constraints, injection rejection,
bounds, JSON/schema and file-member tests.
Verify native: official 26.3+Java 25 disposable free public runner, no implicit
mutation; construct garden; five block assertions; marker; restart checks.
Capture first failure without converting it into success.

Next independent gates: human stock-client visual review, actual player poison,
random-tick crop growth, biome-aware density/placement, palette/resource pack
and three-pack outpost integration. Promotion and physical TrueNAS APPLY HOLD.

Red-team: no fake new block IDs, no automatic destructive installation, no
private GHA costs, no production activation. Blue-team: a deterministic compiler,
five distinct samples and reused established runtime/oracle tooling.
