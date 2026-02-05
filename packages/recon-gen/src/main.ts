#!/usr/bin/env node
import { Effect, } from "effect";
import { NodeContext, NodeRuntime } from "@effect/platform-node"
import { Tools, Transform } from "./transform.ts";
import { VFS } from "./vfs.ts";
import { ReconLanguageServer } from "./lsp.ts";
import { ReconEnvBuilder } from "./env.ts";
import { ReconInitializer } from "./initializer.ts";

const main = Effect.gen(function* () {
    yield* ReconInitializer.init
}).pipe(
    Effect.provide(ReconInitializer.Default),
    Effect.provide(Transform.Default),
    Effect.provide(ReconEnvBuilder.Default),
    Effect.provide(ReconLanguageServer.Default),
    Effect.provide(VFS.Default),
    Effect.provide(Tools.Default),
)

NodeRuntime.runMain(
    main.pipe(
        Effect.provide(NodeContext.layer)
    )
);
