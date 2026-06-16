#!/usr/bin/env bun
import { Console, Effect } from "effect";
import { CliConfig, Command } from "@effect/cli";
import { BunContext, BunRuntime } from "@effect/platform-bun";

import { Tools, Transform } from "@jdsl/jdsl-gen/transform";
import { VFS } from "@jdsl/jdsl-gen/vfs";
import { ReconEnvBuilder } from "@jdsl/jdsl-gen/env";
import { ReconLanguageServer } from "@jdsl/jdsl-gen/lsp";
import { ReconInitializer } from "@jdsl/jdsl-gen/initializer";

if (import.meta.main) {
    const jdsl = Command.make("jdsl", {}, () => ReconInitializer.init);

    const jdslRun = Command.make("run", {}, () => Console.log("JDSL RUN COMMAND"));

    const jdslConfig = Command.make("config", {}, () => Console.log("JDSL CONFIG COMMAND"));
    const command = jdsl.pipe(
        Command.withSubcommands([jdslRun, jdslConfig])
    );
    const cli = Command.run(command, {
        name: "JDSL CLI",
        version: "0.1.0",
    })

    cli(process.argv).pipe(
        Effect.provide(ReconInitializer.Default),
        Effect.provide(Transform.Default),
        Effect.provide(ReconEnvBuilder.Default),
        Effect.provide(ReconLanguageServer.Default),
        Effect.provide(VFS.Default),
        Effect.provide(Tools.Default),
        Effect.catchAll((e) =>
            Effect.sync(() => {
                if (typeof e === "object" && e !== null && "msg" in e) {
                    console.error(String(e.msg));
                    return;
                }

                console.error(String(e));
            }),
        ),
        Effect.provide(BunContext.layer),
        Effect.provide(CliConfig.layer({ showBuiltIns: false })),
        BunRuntime.runMain
    )
}
