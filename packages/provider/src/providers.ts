import { Data, Effect, Either } from "effect";
import type { Providers } from "./config.ts";
import { ModelsDev } from "./models/models-dev.ts";

export class AiProviderError extends Data.TaggedError("AiProviderError")<{ msg: string}> { }
export class AiProvider extends Effect.Service<AiProvider>()(
    "AiProvider",
    {
        effect: Effect.gen(function*(){
            const modelsDev = yield* ModelsDev;
            let provider: Providers = "recon";
            let modelName: string = "";

            const chooseProvider = (name: Providers) => Effect.gen(function*() {
                const providers = yield* modelsDev.listProviders();
                if (!providers.includes(name)) {
                    return yield* new AiProviderError({msg: `${name} is not a supported provider`});
                }
                provider = name;
            })

            const chooseModel = (name: string) => Effect.gen(function* () {
                const modelList = yield* listModels();
                if (!modelList.includes(name)) {
                    return yield* new AiProviderError({msg: `${getProvider()} does not have a model ${name}`});
                }
                modelName = name
            })

            const getProvider = () => Effect.succeed(provider);
            const getModelName = () => Effect.gen(function* (){
                yield* chooseModel(modelName);
                return modelName
            })

            const listModels = () => Effect.gen(function* () {
                const models = yield* Effect.either(modelsDev.getProvider(provider));
                if (Either.isLeft(models)) {
                    return [] as string[];
                }
                return Object.keys(models.right.models);
            });

            return {chooseModel, chooseProvider, getModelName, getProvider, listModels} as const;
        })
    }
){}