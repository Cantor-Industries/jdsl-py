import { homedir } from "os";
import { dirname } from "path";

import { Either, Effect, Schema } from "effect";
import { FileSystem, Path } from "@effect/platform";

const ProviderConfig = Schema.Struct({
    apiKey: Schema.optional(Schema.String),
    authToken: Schema.optional(Schema.String)
})

export type Providers = "Anthropic" | "Google" | "Openai"

const ConfigSchema = Schema.Struct({
    "Anthropic": Schema.optional(ProviderConfig),
    "Google": Schema.optional(ProviderConfig),
    "Openai": Schema.optional(ProviderConfig)
})

interface Config extends Schema.Schema.Type<typeof ConfigSchema> {}

export class AiModelConfig extends Effect.Service<AiModelConfig>()(
    "AiModelConfig",
    {
        effect: Effect.gen(function* () {
            const fs = yield* FileSystem.FileSystem;
            const path = yield* Path.Path;
            let config: Config;

            const home = homedir();
            const configFilename = "auth.json";
            const configDir = ".local/share/recon";
            const configPath = path.join(home, configDir, configFilename);

            const openConfig = (filePath: string) => Effect.gen(function* () {
                const configResult = yield* fs.readFileString(filePath);
                const parsedJsonObj = JSON.parse(configResult);
                const config = yield* Schema.decode(ConfigSchema)(parsedJsonObj);
                return config as Config;
            })

            const saveConfig = (cfg: Config) => Effect.gen(function*() {
                const oldConfig = yield* Effect.either(openConfig(configPath));
                let newConfig: Config;

                if (Either.isLeft(oldConfig)) {
                    newConfig = {};
                } else {
                    const encodedConfig = yield* Schema.encode(ConfigSchema)(cfg);
                    newConfig = {...oldConfig.right, ...encodedConfig };
                }
                config = newConfig;
                const jsonString = JSON.stringify(newConfig, null, 2);

                const dirPath = dirname(configPath);
                const dirExists = yield* fs.exists(dirPath);
                if (!dirExists) {
                    yield* fs.makeDirectory(dirPath, {recursive: true});
                }

                yield* fs.writeFileString(configPath, jsonString, );
            })

            const forProvider = (provider: Providers) => Effect.succeed(config[provider] ?? {})

            const configResult = yield* Effect.either(openConfig(configPath));
            if (Either.isLeft(configResult)) {
                console.log("No config found")
                yield* saveConfig({});
                config = {};
            } else {
                config = configResult.right;
            }

            return { config, forProvider, saveConfig } as const;
        })
    }
) { }
