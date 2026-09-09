# Harness Compiler API

This page renders the harness and compiler source APIs directly from code. It is
the closest analogue to tinygrad's source-backed developer pages.

## Capture

::: jdsl_harness.capture
    options:
      members:
        - CaptureCoordinator

::: jdsl_harness.store
    options:
      members:
        - HarnessStore

::: jdsl_harness.gateway
    options:
      members:
        - ToolGateway

::: jdsl_harness.server
    options:
      members:
        - IngestServer
        - build_mcp_server

## Compiler Passes

::: jdsl_harness.compiler.normalize
    options:
      members:
        - NormStep
        - ModelDecision
        - NormEpisode
        - normalize_episode
        - normalize_all
        - synth_store
        - synth_node_id

::: jdsl_harness.compiler.lineage
    options:
      members:
        - is_meaningful
        - find_source
        - find_all_sources

::: jdsl_harness.compiler.candidates
    options:
      members:
        - Fact
        - extract_facts

::: jdsl_harness.compiler.consolidate
    options:
      members:
        - Evidence
        - Candidate
        - consolidate

::: jdsl_harness.compiler.staticize
    options:
      members:
        - CompiledBehavior
        - staticize

::: jdsl_harness.compiler.residualize
    options:
      members:
        - residualize_decision

::: jdsl_harness.compiler.verify
    options:
      members:
        - VerificationReport
        - verify
        - promote_replay_verified

::: jdsl_harness.compiler.package
    options:
      members:
        - compile_behavior
        - CompileResult
        - build_package

## Host Adapters

::: jdsl_harness.adapters.correlation
    options:
      members:
        - ToolCallCorrelator
        - host_call_id

::: jdsl_harness.adapters.claude_code
    options:
      members:
        - to_events

::: jdsl_harness.adapters.gemini_cli
    options:
      members:
        - to_events

::: jdsl_harness.adapters.opencode
    options:
      members:
        - OpenCodeEnvelopeError
        - to_events

::: jdsl_harness.mcp_proxy
    options:
      members:
        - ProxiedTool
        - MCPProxy
        - StdioUpstream
        - record_proxied_call
        - build_stdio_proxy_server
        - discover_stdio_tools
        - call_stdio_tool
        - serve_proxy
