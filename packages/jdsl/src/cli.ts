import { Console, Effect, } from "effect";
import { AiModelConfig } from "@jdsl/provider/config";

interface AddOptions {
	provider: string;
	apiKey: string[];
}

export class JdslConfig extends Effect.Service<JdslConfig>()("jdsl/config", {
	accessors: true,
	effect: Effect.gen(function* () {
		const config = yield* AiModelConfig;

		const add = ({ apiKey, provider }: AddOptions) => Effect.gen(function* () {
			// yield* Effect.forEach(apiKey, (key) => Effect.gen(function* () {
			// 	yield* config.saveConfig({ [provider!]: { apiKey: [key] } });
			// }));
			console.log(apiKey)
			yield* config.saveConfig({ [provider!]: { apiKey: apiKey } });

			console.log("Api/AuthKey Saved");
		});

		const list = () => Effect.gen(function* () {
			console.log(yield* config.listConfig());
		})
		return { add, list } as const;
	}),
}) { }
