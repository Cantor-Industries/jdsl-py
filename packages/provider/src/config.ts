import { homedir } from "os";
import { dirname } from "path";

import { Either, Effect, Schema } from "effect";
import { FileSystem, Path } from "@effect/platform";
import { AiProvider } from "./providers.ts";

export const ProvidersList = Schema.Literal("anthropic", "deepseek", "google", "nvidia", "openai", "recon", "zhiphu", "z.ai");
export type Providers = typeof ProvidersList.Type;

const ProviderConfig = Schema.Struct({
    apiKey: Schema.optional(Schema.String),
    authToken: Schema.optional(Schema.String)
})

const ConfigSchema = Schema.Struct({
    "anthropic": Schema.optional(ProviderConfig),
    "deepseek": Schema.optional(ProviderConfig),
    "google": Schema.optional(ProviderConfig),
    "nvidia": Schema.optional(ProviderConfig),
    "openai": Schema.optional(ProviderConfig),
    "recon": Schema.optional(ProviderConfig),
    "zhiphu": Schema.optional(ProviderConfig),
    "z.ai": Schema.optional(ProviderConfig),
})

interface Config extends Schema.Schema.Type<typeof ConfigSchema> { }

export class AiModelConfig extends Effect.Service<AiModelConfig>()(
    "AiModelConfig",
    {
        effect: Effect.gen(function* () {
            const fs = yield* FileSystem.FileSystem;
            const path = yield* Path.Path;
            const provider = yield* AiProvider;

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

            const saveConfig = (cfg: Config) => Effect.gen(function* () {
                const oldConfig = yield* Effect.either(openConfig(configPath));
                let newConfig: Config;

                if (Either.isLeft(oldConfig)) {
                    newConfig = {};
                } else {
                    const encodedConfig = yield* Schema.encode(ConfigSchema)(cfg);
                    newConfig = { ...oldConfig.right, ...encodedConfig };
                }
                config = newConfig;
                const jsonString = JSON.stringify(newConfig, null, 2);

                const dirPath = dirname(configPath);
                const dirExists = yield* fs.exists(dirPath);
                if (!dirExists) {
                    yield* fs.makeDirectory(dirPath, { recursive: true });
                }

                yield* fs.writeFileString(configPath, jsonString,);
            })

            const getConfig = () => Effect.gen(function* () {
                const currentProvider = yield* provider.getProvider()
                return config[currentProvider] ?? {}
            })

            const listConfig = () => Effect.gen(function* () {
                return config;
            })

            const configResult = yield* Effect.either(openConfig(configPath));
            if (Either.isLeft(configResult)) {
                yield* saveConfig({});
                config = {};
            } else {
                config = configResult.right;
            }

            return { getConfig, listConfig, saveConfig } as const;
        })
    }
) { }
