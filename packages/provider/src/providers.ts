import { Effect, Either } from "effect";
import type { Providers } from "@jdsl/router/config";
import { type Model, ModelsDev } from "@jdsl/router/models-dev";
import { NoSuchModelError, NoSuchProviderError } from "@jdsl/router/error";

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
                    return yield* new NoSuchProviderError({name: name, msg: `${name} is not a supported provider`, isRetryable: false});
                }
                provider = name;
            })

            const chooseModel = (name: string) => Effect.gen(function* () {
                const modelList = yield* listModels();
                if (!modelList.includes(name)) {
                    return yield* new NoSuchModelError({name: name, msg: `${yield* getProvider()} does not have a model called ${name}`, isRetryable:  false})
                }
                //remember to update provider if not automatically chosen
                modelName = name;
            })

            const getProvider = () => Effect.succeed(provider);

            const getModelName = () => Effect.gen(function* (){
                yield* chooseModel(modelName);
                return modelName
            })

            const getModelSpecs = () => Effect.gen(function* () {
                const results = yield* modelsDev.getProvider(provider);
                const modelSpecs = results.models[modelName];

                if (!modelSpecs) {
                    return yield* new NoSuchModelError({name: modelName, msg: `${getProvider()} does not have a model ${modelName}`, isRetryable: false})
                }
                return modelSpecs as Model;
            })

            const listModels = () => Effect.gen(function* () {
                const models = yield* Effect.either(modelsDev.getProvider(provider));
                if (Either.isLeft(models)) {
                    return [] as string[];
                }
                return Object.keys(models.right.models);
            });

            return {chooseModel, chooseProvider, getModelName, getModelSpecs, getProvider, listModels} as const;
        })
    }
){}