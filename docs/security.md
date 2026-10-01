# Harness Security Model

This document describes the current trust boundaries of the JDSL harness. It is
an inventory of assets, actors, and controls, not a claim that the harness is a
sandbox or a multi-user service.

## Scope

The harness is designed for local development and controlled package execution.
The default ingest server binds to loopback. The host tools file, predicate file,
and model adapter are trusted local code supplied by the operator. A `.jdsl`
package is not trusted merely because it loads successfully; package validation
checks structure and digests, while host bindings still determine what external
side effects are possible.

## Assets and Boundaries

| Asset or boundary | Current exposure | Current control | Remaining risk |
| --- | --- | --- | --- |
| Ingest daemon | Local HTTP server receives canonical events and host hook payloads. | Loopback-only binding, per-capture tokens, allowed-origin checks, request-size limits, and per-capture rate limits. Malformed adapter requests fail open to the host with an error response; authentication failures are rejected. | Capture listing and summaries are still local unauthenticated reads, and there is no multi-user authorization model. |
| Captured events | Tool arguments, results, messages, state references, and blobs may contain secrets, PII, or attacker-controlled text. | `Redactor` supports secret patterns, key names, and configured JSON paths. | Redaction is not automatically applied to every durable store write. Operators must not treat captures as sanitized by default. |
| SQLite and JSONL store | Capture metadata and append-only event spools are written under `JDSL_HARNESS_HOME`. | Local filesystem permissions and hash-chained trace events. | No retention policy, quota, repair command, or multi-user isolation. |
| Compiler input | Normalization and candidate extraction consume captured events. | The baseline compiler is heuristic and deterministic; compiled structure is built from a closed Behavior IR vocabulary. | Captured content is still untrusted data. Model-backed compiler roles need evidence delimiting and deterministic proposal verification before use. |
| `.jdsl` package | Archives may be received from another person or process. | Manifest digests, format checks, IR validation, safe guard-expression language, and no host-code imports. | No signing, archive resource limits, explicit schema limits, or package policy requiring trusted signatures. |
| Host bindings | `TOOLS`, `PREDICATES`, and model adapters are imported local Python code. | Package names logical capabilities; binding fails when required capabilities are missing. | These files are trusted code and are not sandboxed by the package runtime. |
| Package runtime | Bound tools and residual model leaves can perform effects requested by the policy. | Capability binding, tool contracts, structural validation, and explicit effect metadata. | Effect enforcement, dry-run mode, per-run budgets, and process isolation are not complete. |

## Actors

- **Operator:** controls the local checkout, credentials, host bindings, and
  package execution environment.
- **Host plugin or hook:** forwards observations from Claude Code, Gemini CLI, or
  OpenCode. Host-side shims fail open so telemetry failure does not block the
  host operation.
- **Local process or browser:** may reach a loopback HTTP service unless the
  operator adds external isolation. Event writes require the per-capture token.
- **Captured task or tool result:** may contain prompt-injection text. It is
  evidence for compilation, not trusted compiler instructions.
- **Package author or distributor:** may provide a malformed or unsafe policy;
  digest verification authenticates file consistency, not correctness or origin.
- **Host tool author:** supplies the trusted callable implementations that are
  bound to logical capabilities at runtime.

## Current Non-Goals

The current harness does not claim to provide:

- a network-exposed or multi-user secure ingest service;
- a sandbox for Python tool bindings or model adapters;
- automatic secret removal from every capture path;
- cryptographic package signing or publisher identity;
- universal correctness proof from replay;
- protection against a compromised operator account or filesystem.

## Security Work Queue

The next security changes should be delivered as independently tested slices:

1. Apply shared redaction before durable persistence and record the policy in
   capture metadata.
2. Harden package loading and resource limits, with distinct validation errors.
3. Enforce runtime effect policies, dry-run behavior, and per-run budgets.
4. Add package signatures and provenance that records capture, compiler, redaction,
   and verification identities.

Each change should add happy-path and failure-path tests and update this threat
model when it changes a trust boundary.
