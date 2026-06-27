#!/usr/bin/env bun
import { Console, Effect } from "effect";
import { Args, CliConfig, Command, Options } from "@effect/cli";
import { BunContext, BunRuntime } from "@effect/platform-bun";

import { Tools, Transform } from "@jdsl/jdsl-gen/transform";
import { VFS } from "@jdsl/jdsl-gen/vfs";
import { ReconEnvBuilder } from "@jdsl/jdsl-gen/env";
import { ReconLanguageServer } from "@jdsl/jdsl-gen/lsp";
import { ReconInitializer } from "@jdsl/jdsl-gen/initializer";
import { AiModelConfig } from "@jdsl/provider/config";
import { AiProvider } from "@jdsl/provider/providers";
import { ModelsDev } from "@jdsl/provider/models-dev";

import { JdslConfig } from "./cli.ts";

if (import.meta.main) {

    const provider = Options.text("provider").pipe(Options.withAlias("p"));
    const apiKey = Args.text({name: "apiKey"}).pipe( Args.atLeast(1) );
    const addConfig = Command.make("add", { provider, apiKey }, JdslConfig.add);

    const listConfig = Command.make("list", {}, JdslConfig.list);

    const jdslConfig = Command.make("config").pipe(
        Command.withSubcommands([addConfig, listConfig]),
    );

    // const jdslRun = Command.make("run", {}, () => Console.log("JDSL RUN COMMAND"));

    const command = Command.make("jdsl", {}, () => ReconInitializer.init).pipe(
        Command.withSubcommands([jdslConfig])
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
        Effect.provide(JdslConfig.Default),
        Effect.provide(AiModelConfig.Default),
        Effect.provide(AiProvider.Default),
        Effect.provide(ModelsDev.Default),
        Effect.catchAll((e) =>
            Effect.sync(() => {
                console.error(e)
                if (typeof e === "object" && e !== null && "msg" in e) {
                    console.error(String(e), String(e.msg));
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
