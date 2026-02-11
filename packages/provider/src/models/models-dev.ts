import { homedir } from "os";
import { dirname } from "path";
import { stat } from "fs";
import { promisify } from "util";

import { Data, Effect, Either, Schema } from "effect";
import { FileSystem, Path } from "@effect/platform";

import { type ModelProviders, type Provider, ModelsDevSchema } from "./modelSchema";
import type { Providers } from "../config";

const CacheMetadataSchema = Schema.Struct({
    size: Schema.Number,
    modified: Schema.Date,
    created: Schema.Date
})
interface CacheMetadata extends Schema.Schema.Type<typeof CacheMetadataSchema> { }

export class ModelsDevError extends Data.TaggedError("ModelsDevError")<{ msg: string, error?: unknown }> { }
export class HttpError extends Data.TaggedError("HttpError")<{ status: number, statusText: string }> { }
export class JSONParseError extends Data.TaggedError("JSONParseError")<{ error: unknown }> { }
export class FetchError extends Data.TaggedError("FetchError")<{ error: unknown }> { }
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
                            throw new JSONParseError({ error })
                        }
                    },
                    catch: (error) => {
                        if (error instanceof HttpError || error instanceof JSONParseError) {
                            return error
                        }
                        return new FetchError({ error })
                    }
                })

                const models = yield* getModels
                const result = yield* Schema.encode(ModelsDevSchema)(models);
                return result as ModelProviders
            })

            const updateModels = Effect.gen(function* () {
                const cacheStats = yield* Effect.either(getCacheMetadata());
                const now = new Date();
                const ttlInMillis = 24 * 3600 * 1000;
                if (Either.isRight(cacheStats)) {
                    const stats = cacheStats.right;
                    const elapsedTime = now.getTime() - Date.parse(stats.modified);
                    if (elapsedTime > ttlInMillis) {
                        return true;
                    }
                }
                return false
            })

            const getCacheMetadata = () => Effect.gen(function* () {
                const fromAsync = (path: string) => Effect.tryPromise(async () => {
                    const statPromise = promisify(stat);
                    return await statPromise(path);
                })
                const stats = yield* fromAsync(modelCachePath)
                return yield* Schema.encode(CacheMetadataSchema)({ size: stats.size, modified: stats.mtime, created: stats.ctime });
            })

            const getProvider = (provider: Providers) => Effect.gen(function* () {
                const results = models[provider];
                if (!results) {
                    return yield* new ModelsDevError({ msg: `invalid ${provider}. Could not find ${provider} on models.dev providers` })
                }
                return results as Provider
            });

            const listProviders = () => Effect.sync(() => {
                return Object.keys(models);
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
            }
            else {
                const status = yield* updateModels;
                if (status) {
                    models = yield* fetchModels;
                    yield* saveModelCache(models);
                } else {
                    models = modelsCache.right
                }
            }
            return { getProvider, listProviders } as const
        })
    }
) { }