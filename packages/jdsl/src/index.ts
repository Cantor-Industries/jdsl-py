#!/usr/bin/env bun
import { Console, Effect, Option } from "effect";
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
    const choice = Args.choice([
        ["add", "add"],
        ["list", "list"],
        ["update", "update"],
        ["remove", "remove"],
    ]);
    const provider = Options.text("provider").pipe(Options.withAlias("p"), Options.optional);
    const apiKey = Options.text("apiKey").pipe(Options.withAlias("k"), Options.optional);
    const auth = Options.text("auth").pipe(Options.withAlias("a"), Options.optional);
    const jdslConfig = Command.make("config", { choice, provider, auth, apiKey }, JdslConfig.choice);

    const jdslRun = Command.make("run", {}, () => Console.log("JDSL RUN COMMAND"));

    const jdsl = Command.make("jdsl", {}, () => ReconInitializer.init);
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
        Effect.provide(JdslConfig.Default),
        Effect.provide(AiModelConfig.Default),
        Effect.provide(AiProvider.Default),
        Effect.provide(ModelsDev.Default),
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
