#!/usr/bin/env bun
import { Effect } from "effect";
import { BunContext, BunRuntime } from "@effect/platform-bun";

import { ReconCli } from "./cli.ts";

if (import.meta.main) {
    const main = Effect.gen(function* () {
        const cli = yield* ReconCli;
        yield* cli.run(Bun.argv.slice(2));
    }).pipe(
        Effect.provide(ReconCli.Default),
    )

    BunRuntime.runMain(
        main.pipe(
            Effect.provide(BunContext.layer)
        ) as Effect.Effect<void, never, never>
    );
}