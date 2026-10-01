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
