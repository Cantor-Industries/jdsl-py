import { Data, Effect } from "effect";
import { BunRuntime, BunContext } from "@effect/platform-bun";

import { createGoogleGenerativeAI, google } from "@ai-sdk/google";
import { createOpenAI } from "@ai-sdk/openai";
import { createAnthropic } from "@ai-sdk/anthropic";

import { AiModelConfig } from "./config";
import { AiProvider } from "./providers";
import { ModelsDev } from "./models-dev";

export class AiError extends Data.TaggedError("AiError")<{msg: string}>{}
export class AiModel extends Effect.Service<AiModel>()(
    "AiModel",
    {
        effect: Effect.gen(function* () {
            const modelConfig = yield* AiModelConfig;
            const modelProvider = yield* AiProvider;

            yield* modelProvider.chooseProvider("google");
            yield* modelProvider.listModels()
            const config = yield* modelConfig.getConfig();

            let model;

            return {model} as const;
        })
    }
){}

const program = Effect.gen(function* () {
    const aiModel = yield* AiModel
}).pipe(
    Effect.provide(AiModel.Default),
    Effect.provide(AiModelConfig.Default),
    Effect.provide(AiProvider.Default),
    Effect.provide(ModelsDev.Default)
)

BunRuntime.runMain(program.pipe(Effect.provide(BunContext.layer)))