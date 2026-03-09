#!/usr/bin/env bun
import { Effect } from "effect";
import { BunContext, BunRuntime } from "@effect/platform-bun";

import { Tools, Transform } from "@jdsl/recon-gen/transform";
import { VFS } from "@jdsl/recon-gen/vfs";
import { ReconEnvBuilder } from "@jdsl/recon-gen/env";
import { ReconLanguageServer } from "@jdsl/recon-gen/lsp";
import { ReconInitializer } from "@jdsl/recon-gen/initializer";

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

BunRuntime.runMain(
    main.pipe(
        Effect.provide(BunContext.layer)
    )
);
