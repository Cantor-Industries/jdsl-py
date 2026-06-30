import { homedir } from "os";
import { dirname } from "path";

import { Effect, Schema } from "effect";
import { FileSystem, Path } from "@effect/platform";
import { LoadAPIKeyError } from "./types.ts";

export const ProvidersList = Schema.Literal("anthropic", "deepseek", "google", "nvidia", "openai", "recon", "zhipuai", "zai", "zai-coding-plan", "zhipuai-coding-plan");
export type Providers = typeof ProvidersList.Type;

const ProviderConfig = Schema.Struct({
    apiKey: Schema.Array(Schema.String),
});

const ConfigSchema = Schema.Struct({
    "anthropic": Schema.optional(ProviderConfig),
    "deepseek": Schema.optional(ProviderConfig),
    "google": Schema.optional(ProviderConfig),
    "nvidia": Schema.optional(ProviderConfig),
    "openai": Schema.optional(ProviderConfig),
    "recon": Schema.optional(ProviderConfig),
    "zhipuai": Schema.optional(ProviderConfig),
    "zai": Schema.optional(ProviderConfig),
    "zai-coding-plan": Schema.optional(ProviderConfig),
    "zhipuai-coding-plan": Schema.optional(ProviderConfig),
})

interface Config extends Schema.Schema.Type<typeof ConfigSchema> { }

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
            });

            const saveConfig = (cfg: Config) => Effect.gen(function* () {
                let newCfg: Config = {};
                const providers = Object.keys(cfg);
                for (const provider of providers) {
                    newCfg = {
                        ...config, 
                        [provider]: {apiKey: Array.from(new Set([...config[provider as Providers]?.apiKey ?? [], ...cfg[provider as Providers]!.apiKey]))}
                    }
                }
                config = newCfg;
                const jsonString = JSON.stringify(newCfg, null, 2);

                const dirPath = dirname(configPath);
                const dirExists = yield* fs.exists(dirPath);
                if (!dirExists) {
                    yield* fs.makeDirectory(dirPath, { recursive: true });
                }

                yield* fs.writeFileString(configPath, jsonString,);
            });

            const getConfig = (provider: Providers) => Effect.gen(function* () {
                const cfg = config[provider];
                return cfg ? cfg : yield* new LoadAPIKeyError({name: "AiModelConfig", msg: `${provider} apiKey/auth is missing`, isRetryable: false})
            });

            const listConfig = () => Effect.gen(function* () {
                return config;
            });

            config = yield* openConfig(configPath);

            return { getConfig, listConfig, saveConfig } as const;
        })
    }
) { }
