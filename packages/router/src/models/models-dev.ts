import { homedir } from "os";

import { Data, Effect, Option, Schema } from "effect";
import { FileSystem, Path } from "@effect/platform";

import { type ModelProviders, type Provider, ModelsDevSchema } from "./modelSchema.ts";
import type { Providers } from "../config.ts";
import { NoSuchModelError } from "../types.ts";
export { type Model } from "./modelSchema.ts";

export class FetchError extends Data.TaggedError("FetchError")<{ name: string, msg: string, isRetryable: boolean }> { }
export class CacheError extends Data.TaggedError("CacheError")<{ msg: string }> { }

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
                const getModels = Effect.tryPromise(async () => {
                    const url = "https://models.dev/api.json";
                    const response = await fetch(url);
                    const jsonResponse = await response.json() as any;
                    return jsonResponse;
                }).pipe(
                    Effect.mapError(e => {
                        new FetchError({name: "FetchError", msg: e.message, isRetryable: true});
                    })
                );
                const models = yield* getModels
                const result = yield* Schema.decode(ModelsDevSchema)(models);
                return result as ModelProviders
            })

            const saveModelCache = (models: ModelProviders) => Effect.gen(function* () {
                const dirPath = path.dirname(modelCachePath);
                const dirExists = yield* fs.exists(dirPath);
                const jsonString = JSON.stringify(models, null, 2);
                if (!dirExists) {
                    yield* fs.makeDirectory(dirPath, { recursive: true });
                }
                yield* fs.writeFileString(modelCachePath, jsonString);
            })

            const openModelCache = (filePath: string) => Effect.gen(function* () {
                const stats = yield* fs.stat(filePath)
                const now = new Date();
                const ttlInMillis = 24 * 3600 * 1000;
                const modifiedTime = Option.getOrThrow(stats.mtime);
                if ((modifiedTime.getTime() - now.getTime()) > ttlInMillis) {
                    return yield* new CacheError({ msg: "Saved models cache has expired and should be updated" })
                }

                const cacheResult = yield* fs.readFileString(filePath);
                const parsedJsonObj = JSON.parse(cacheResult);
                const cache = yield* Schema.decode(ModelsDevSchema)(parsedJsonObj);
                return cache as ModelProviders
            });

            const getProvider = (provider: Providers) => Effect.gen(function* () {
                const results = models[provider];
                if (!results) {
                    return yield* new NoSuchModelError({ name: "NoSuchModelError", msg: `invalid ${provider}. Could not find ${provider} on models.dev providers`, isRetryable: false })
                }
                return results as Provider
            });

            const listProviders = () => Effect.sync(() => {
                return Object.keys(models);
            });

            models = yield* openModelCache(modelCachePath).pipe(
                Effect.catchAll(() => Effect.gen(function* () {
                    const modelsCache = yield* fetchModels;
                    yield* saveModelCache(modelsCache);
                    return modelsCache;
                }))
            )

            return { getProvider, listProviders } as const;
        })
    }
) { }