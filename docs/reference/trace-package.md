# Trace and Package API

This page renders the tracing, IR, and package source APIs directly from code.

## Trace Events

::: jdsl.trace.events
    options:
      members:
        - SCHEMA_VERSION
        - EventKind
        - EventSource
        - TraceEvent

## Trace Sinks

::: jdsl.trace.sink
    options:
      members:
        - TraceSink
        - NullTraceSink
        - ListTraceSink
        - SafeSink
        - FanoutSink

## JSONL and Replay

::: jdsl.trace.jsonl
    options:
      members:
        - JsonlTraceSink
        - read_events
        - iter_events
        - verify_chain

::: jdsl.trace.replay
    options:
      members:
        - ToolInvocation
        - Episode
        - segment_episodes

## Behavior IR

::: jdsl.ir.schema
    options:
      members:
        - SignatureInput
        - SignatureOutput
        - Signature
        - IRNode
        - IRSequence
        - IRSelector
        - IROptional
        - IRInvert
        - IRRepeat
        - IRAction
        - IRGuard
        - IRGuardCall
        - IRPredict
        - IRReact
        - BehaviorIR

::: jdsl.ir.expr
    options:
      members:
        - ExprError
        - resolve_path
        - evaluate
        - validate_expr

::: jdsl.ir.lower
    options:
      members:
        - BindingError
        - RuntimeBindings
        - lower
        - lower_node

## Packages

::: jdsl.package.manifest
    options:
      members:
        - ToolEffects
        - ToolContract
        - NodeProvenance
        - Manifest

::: jdsl.package.export
    options:
      members:
        - BehaviorPackage
        - export_dir
        - export_jdsl
        - package_digest

::: jdsl.package.load
    options:
      members:
        - PackageError
        - LoadedPackage
        - load_package
