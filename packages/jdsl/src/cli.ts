import { Effect, Schema } from "effect";
import { AiModelConfig } from "@jdsl/router/config";
import { ProvidersList } from "@jdsl/router/config";
import { NoSuchProviderError } from "@jdsl/router/error";

interface AddOptions {
	provider: string;
	apiKey: string[];
}

export class JdslConfig extends Effect.Service<JdslConfig>()("jdsl/config", {
	accessors: true,
	effect: Effect.gen(function* () {
		const config = yield* AiModelConfig;

		const add = ({ apiKey, provider }: AddOptions) => Effect.gen(function* () {
			if (!Schema.is(ProvidersList)(provider)) {
				return yield* new NoSuchProviderError({ name: "NoSuchProviderEror", msg: `No provider named: ${provider} is currently supported`, isRetryable: false })

			}
			yield* config.saveConfig({ [provider]: { apiKey: apiKey } });

			console.log("Api/AuthKey Saved");
		});

		const list = () => Effect.gen(function* () {
			console.log(yield* config.listConfig());
		})
		return { add, list } as const;
	}),
}) { }
