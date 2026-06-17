import { Effect, Option } from "effect";
import { AiModelConfig } from "@jdsl/provider/config";

interface ChoiceOptions {
	choice: string;
	provider: Option.Option<string>;
	auth: Option.Option<string>;
	apiKey: Option.Option<string>
}

export class JdslConfig extends Effect.Service<JdslConfig>()("jdsl/config", {
	accessors: true,
	effect: Effect.gen(function* () {
		const config = yield* AiModelConfig;
		const choice = ({ apiKey, auth, choice, provider }: ChoiceOptions) => Effect.gen(function* () {
			const providerName = Option.match(provider, {
				onNone: () => undefined,
				onSome: (name) => name
			})

			const apiKeyName = Option.match(apiKey, {
				onNone: () => undefined,
				onSome: (name) => name
			})

			const authName = Option.match(auth, {
				onNone: () => undefined,
				onSome: (name) => name
			})

			if (choice === "list") {
				console.log(yield* config.listConfig());
			} else if (choice === "add") {
				console.log(providerName, apiKeyName, authName);
				
				yield* config.saveConfig({[providerName!]: {apiKey: apiKeyName}});
			}
		})
		return { choice } as const;
	}),
}) { }
