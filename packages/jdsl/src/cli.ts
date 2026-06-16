import { Command } from "commander";
import { Effect } from "effect";

import { Tools, Transform } from "@jdsl/jdsl-gen/transform";
import { VFS } from "@jdsl/jdsl-gen/vfs";
import { ReconEnvBuilder } from "@jdsl/jdsl-gen/env";
import { ReconLanguageServer } from "@jdsl/jdsl-gen/lsp";
import { ReconInitializer } from "@jdsl/jdsl-gen/initializer";

const runRecon = Effect.gen(function* () {
	yield* ReconInitializer.init;
}).pipe(
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
);

export class ReconCli extends Effect.Service<ReconCli>()("recon/Cli", {
	sync: () => ({
		run: (argv: ReadonlyArray<string>) =>
			Effect.gen(function* () {

				const program = new Command()
					.name("recon")
					.description("Recon command line interface");

				program
					.command("run")
					.description("Run recon")
					.action(() => {
					});

				program
					.command("help")
					.description("Recon help utility")
					.action(() => program.outputHelp())

				if (argv.length === 0) {
					yield* runRecon
					return;
				}

				yield* Effect.tryPromise({
					try: () => program.parseAsync([...argv], { from: "user" }),
					catch: (cause) => cause,
				}).pipe(
					Effect.catchAll((cause) =>
						Effect.sync(() => {
							console.error(String(cause));
						}),
					),
				);
			}),
	}),
}) { }
