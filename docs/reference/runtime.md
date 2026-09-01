# Runtime API

This page is generated from the runtime source with `mkdocstrings`. The narrative
walkthroughs explain why the pieces exist; this reference exposes the callable
surface and implementation docstrings directly from code.

## Authoring DSL

::: jdsl.dsl
    options:
      members:
        - Tool
        - tool
        - act
        - ref
        - store
        - seq
        - sel
        - check
        - guard
        - guard_call
        - repeat
        - invert
        - optional
        - timeout
        - oneshot
        - predict
        - react
        - root

## Runtime Nodes

::: jdsl.tree
    options:
      members:
        - Status
        - Node
        - Action
        - Sequence
        - Selector
        - Repeat
        - Check
        - Guard
        - GuardCall
        - Predict
        - React
        - Invert
        - Optional
        - Timeout
        - OneShot
        - Root

## Runtime State

::: jdsl.context
    options:
      members:
        - Write
        - Blackboard
        - Ref
        - ToolCall
        - ModelTurn
        - ContextWindow
        - RunContext

## Providers

::: jdsl.provider
    options:
      members:
        - LanguageModel
        - DEFAULT_MODEL

::: jdsl.config
    options:
      members:
        - SUPPORTED_PROVIDERS
        - ENV_KEYS
        - BASE_URLS
        - provider_for_model
        - config_dir
        - auth_path
        - load
        - save
        - add_keys
        - keys_for
