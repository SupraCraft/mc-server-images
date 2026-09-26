# Paper runtime contract

## Immutable image

The image layer contains:

- Java 25 JRE;
- one pinned Paper server JAR;
- minimal entrypoint;
- OCI metadata identifying Paper version/build.

It does not contain worlds, credentials, plugins, or consumer-specific
configuration.

## Mutable state

All server state lives under `/data`.

Consumers may mount:

- `/data/plugins`;
- `/data/server.properties`;
- worlds and Paper configuration.

## Startup

Startup fails closed until `EULA=TRUE` is explicitly set.

The entrypoint creates a minimal `server.properties` only when the consumer has
not supplied one.

## Qualification invariant

A tag is qualified only when automation has:

1. resolved the exact stable Paper build through PaperMC's official downloads service;
2. verified the server JAR against PaperMC's published SHA-256;
3. built the image;
4. started a real Paper server;
5. observed the server reach ready state;
6. stopped the server;
7. retained machine-readable evidence.

## Consumer invariant

Consumers pin the build tag or immutable image digest.

No consumer should rely on a mutable `latest` tag for qualification evidence.
