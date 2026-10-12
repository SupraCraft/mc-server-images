# Vanilla 26.3 restoration datapack — portable artifact candidate

**Authority:** [Minecraft hosting deployment #53](https://github.com/SupraCraft/mc-server-images/issues/53); [COLLAGE multi-audience acceptance](https://github.com/SupraCraft/collage-private/issues/3); [Lantern story campaign](https://github.com/SupraCraft/mc-structure-foundry-private/issues/19).

The existing `tools/probe_core_restoration_datapack_26_3.py` authors a functional vanilla datapack into a temporary test world. `tools/export_core_restoration_datapack_26_3.py` calls that exact source generator to publish a **real** deterministic zip, a SHA-256 manifest, target version, source Git commit, world ID and release ID. It does not invent a new datapack language or duplicate the builder.

Run on a checked-out source commit:

```sh
python3 tools/export_core_restoration_datapack_26_3.py \
  --out artifacts/lantern-restoration-26.3.zip \
  --manifest artifacts/lantern-restoration-26.3.json \
  --world-id lantern-rdte --release-id lantern-core-restore-26-3
```

The public workflow `export-core-restoration-artifact-26-3.yml` exercises deterministic byte identity, emits ZIP+manifest, and retains the artifact for bounded download. The artifact contains `pack.mcmeta` and exact 26.3 restoration function/tick files, **not** a saved world or any runtime configuration/secrets. A world or Datapack deployment actuator must still safely unpack with member allowlisting, verify digest and compatibility, stage under that world's `datapacks/`, quiesce/snapshot/activate/resume according to the canonical world-activation transaction, verify actual behavior through independent Java/Gym oracles, and rollback if health/semantic checks fail. This exporter never performs those mutations.

**Audience parity:** humans, CI automation and delegated agents consume the same manifest and immutable ZIP, via thin interfaces over the versioned COLLAGE request contract. Principal declarations are not authentication; admission/approval and operations-vs-RDTE policy remain external and enforced. No inferred privilege from actor kind.

**Admission:**
- `SOURCE_ARTIFACT_EXPORTED` establishes real datapack bytes and checked source provenance **only**. It does **not** establish real world materialization, Two Rivers completion, vanilla 26.3 client behavior during this export, or COLLAGE/TrueNAS deployment.
- The separately qualified exact vanilla 26.3 restoration probe is existing runtime evidence; it does not convert this new ZIP into a deployed-world PASS until that ZIP is independently mounted and evaluated.
- A single completed Lantern restoration example is a first *candidate* for the Two Rivers artifact-consumer seam. It does not stand in for an actual complete Two Rivers world release or for a source-produced MCWORLD world-save.
- Reject digest drift, wrong version/world identity, unsafe archive paths, resource budget violation, unadmitted activation, unexpected world lifecycle or absent post-activation evidence.
- Physical TrueNAS APPLY remains HOLD, and the existing disposable Paper 1.21.11 result does **not** prove vanilla 26.3.

Next: bind the exported artifact and digest to a COLLAGE `collage.deployment-request/1` source plan, then independently qualify staging and activation **on a real disposable vanilla 26.3 world** through the existing world controller, Foundry/runtime and Bot Gym boundaries. Preserve evidence and an explicit rollback receipt.
