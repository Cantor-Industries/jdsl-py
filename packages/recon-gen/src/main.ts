#!/usr/bin/env bun
import { Effect, } from "effect";
import { Tools, Transform } from "./dsl/transform.ts";
import { VFS } from "./lsp/vfs.ts";
import { ReconLanguageServer } from "./lsp/lsp.ts";
import { ReconEnvBuilder } from "./lsp/env.ts";
import { ReconInitializer } from "./initializer.ts";

const main = Effect.gen(function* () {
    yield* ReconInitializer.init;
}).pipe(
    Effect.provide(ReconInitializer.Default),
    Effect.provide(Transform.Default),
    Effect.provide(ReconEnvBuilder.Default),
    Effect.provide(ReconLanguageServer.Default),
    Effect.provide(VFS.Default),
    Effect.provide(Tools.Default),
    Effect.catchAll(e => Effect.sync(() => {
        console.error(e.msg);
    })),
)

// BunRuntime.runMain(
//     main.pipe(
//         Effect.provide(BunContext.layer)
//     )
// );
