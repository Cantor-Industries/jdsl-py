import { homedir } from "os";
import { dirname } from "path";

import { Data, Effect, Either, Schema } from "effect";
import { FileSystem, Path } from "@effect/platform";

import { type ModelProviders, type Models, ModelsDevSchema } from "./modelSchema";
import type { Providers } from "./config";

export class ModelsDevError extends Data.TaggedError("ModelsDevError")<{ msg: string, error?: unknown }> { }
export class HttpError extends Data.TaggedError("HttpError")<{ status: number, statusText: string }> { }
export class JSONParseError extends Data.TaggedError("JSONParseError")<{ error: unknown }> { }
export class FetchError extends Data.TaggedError("FetchError")<{ error: unknown }> { }

export class ModelsDev extends Effect.Service<ModelsDev>()(
    "ModelsDev",
    {
        effect: Effect.gen(function* () {
            const fs = yield* FileSystem.FileSystem;
            const path = yield* Path.Path;

            let models: ModelProviders;

            const home = homedir();
            const modelCacheFilename = "models-dev.json";
            const modelCacheDir = ".local/share/recon"
            const modelCachePath = path.join(home, modelCacheDir, modelCacheFilename);

            const fetchModels = Effect.gen(function* () {
                const getModels = Effect.tryPromise({
                    try: async () => {
                        const url = "https://models.dev/api.json";
                        const response = await fetch(url);
                        if (!response.ok) {
                            throw new HttpError({ status: response.status, statusText: response.statusText })
                        }
                        try {
                            const jsonResponse = await response.json() as any;
                            return jsonResponse;
                        } catch (error) {
                            throw new JSONParseError({error})
                        }
                    },
                    catch: (error) => {
                        if (error instanceof HttpError || error instanceof JSONParseError) {
                            return error
                        }
                        return new FetchError({error})
                    }
                })

                const models = yield* getModels
                const result = yield* Schema.encode(ModelsDevSchema)(models);
                return result as ModelProviders
            })

            const getModels = (provider: Providers) => Effect.gen(function* () {
                const results = models[provider];
                if (!results) {
                    return yield* new ModelsDevError({ msg: `invalid ${provider}. Could not find ${provider} on models.dev providers` })
                }
                return results as Models
            });

            const openModelCache = (filePath: string) => Effect.gen(function* () {
                const cacheResult = yield* fs.readFileString(filePath);
                const parsedJsonObj = JSON.parse(cacheResult);
                const cache = yield* Schema.decode(ModelsDevSchema)(parsedJsonObj);
                return cache as ModelProviders
            })

            const saveModelCache = (models: ModelProviders) => Effect.gen(function* () {
                const dirPath = dirname(modelCachePath);
                const dirExists = yield* fs.exists(dirPath);
                const jsonString = JSON.stringify(models, null, 2);
                if (!dirExists) {
                    yield* fs.makeDirectory(dirPath, { recursive: true });
                }
                yield* fs.writeFileString(modelCachePath, jsonString);
            })

            const modelsCache = yield* Effect.either(openModelCache(modelCachePath))
            if (Either.isLeft(modelsCache)) {
                models = yield* fetchModels;
                yield* saveModelCache(models);
            } else {
                models = modelsCache.right
            }

            return { getModels } as const
        })
    }
) { }