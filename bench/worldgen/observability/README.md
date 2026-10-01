# SupraCraft causal microscope

This directory defines the version-neutral observability contract used by causal
recovery experiments. The stable product surface is the semantic event stream;
a Java agent, JFR consumer, mod/mixin, protocol observer, or client sensor is an
implementation backend.

A trace is newline-delimited JSON. Every line conforms to
supracraft-causal-event/1. A trace begins with trace_start and ends with
trace_end. A missing trace_end, a nonzero dropped_events value, a sequence gap,
or a failed adapter binding makes the trace incomplete for causal promotion.

Required evidence boundaries:

- observed order is not automatically causality;
- source support and runtime support remain separate;
- command payload identity is not execution;
- execution is not packet delivery;
- delivery is not client presentation or human comprehension;
- adapters are exact-version only and fail closed;
- stock vanilla remains the behavioral control;
- raw authored command/chat text is excluded from normal traces.

Observer qualification compares stock vanilla against the same exact executable
with the requested sensor pack attached. Timing overhead is reported separately
from semantic divergence. Alternative servers and modded runtimes may be useful
comparison surfaces but do not silently replace the vanilla oracle.


## Exact-version frontier discovery

A qualified adapter manifest and a frontier discovery receipt are deliberately
different artifacts.

- `supracraft-causal-version-discovery/1` is produced before any version-
  specific direct hooks are trusted. It records exact Mojang artifact
  provenance, required Java, detected symbol mode, the runtime-discovered
  native Minecraft JFR catalog, and conservative semantic coverage gaps.
- `supracraft-causal-capability-manifest/1` is reserved for an exact-version
  adapter whose concrete bindings have been identified and independently
  qualified.

Frontier discovery resolves `latest.release` and `latest.snapshot` from the
official Mojang version manifest at workflow execution time and fails closed if
either frontier changes between resolution and probing. Native JFR event names
are evidence discovered from the exact runtime; they are reported as candidates
until their fields and semantics are independently qualified. Missing coverage
is the input to the next smallest direct-hook sensor pack, not permission to
reuse a nearby version's hooks.
