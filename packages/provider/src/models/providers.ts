import { Effect } from "effect";
import type { Providers } from "./config";
import { ModelsDev } from "./models-dev";

export class AiProvider extends Effect.Service<AiProvider>()(
    "AiProvider",
    {
        effect: Effect.gen(function*(){
            const modelsDev = yield* ModelsDev;
            let provider: Providers = "recon";

            const chooseProvider = (name: Providers) => Effect.sync(() => {
                provider = name;
            })

            const getProvider = () => Effect.succeed(provider);

            const listModels = () => Effect.gen(function* () {
                const models = yield* modelsDev.getModels(provider);
                return Object.keys(models.models);
            })

            return {chooseProvider, getProvider, listModels} as const;
        })
    }
){}