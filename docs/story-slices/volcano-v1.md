# Recurring Resource Volcano v1

This is the first bounded story-to-vanilla systemic-world slice.

## Story intent

A volcano periodically erupts. Each eruption adds persistent material. After cooling, mineable resources exist inside the cooled cone. If the volcano begins underwater, repeated eruptions can grow the cone above the water surface and create an island.

The story intent does not specify Minecraft commands or block layouts.

## First lowering

Minecraft Java 26.3, vanilla datapack, command-orchestrated.

State machine:

`dormant -> warning -> eruption -> cooling -> resource_ready -> dormant`

For the bounded v1 canary, three cycles are generated.

Each cycle:
- increases cone height and radius;
- places temporary lava at the vent;
- cools the lava to obsidian;
- places deterministic mineable ore inside persistent basalt/blackstone terrain;
- records observable log markers.

The underwater profile defines island emergence as persistent volcano geometry crossing `water_surface_y + 1`.

## Why this is a useful vertical slice

It exercises:
- story lifecycle/timing;
- persistent world mutation;
- cumulative state;
- transformation from hot/erupted to cooled/resource-bearing state;
- observation/feedback;
- environmental threshold logic;
- exact-version vanilla artifact generation.

## Deliberate limitations

The command-orchestrated implementation is not a geology claim.

It does not yet model:
- tectonics;
- pressure;
- natural lava-fluid propagation;
- ash/falling material physics;
- realistic erosion/cooling;
- geologically realistic ore placement;
- automatic site selection from arbitrary terrain.

Those are future lowering improvements. They do not require changing the story intent.
