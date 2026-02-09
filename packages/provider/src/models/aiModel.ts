import { Data, Effect } from "effect";
import { createGoogleGenerativeAI, google } from "@ai-sdk/google";
import { createOpenAI } from "@ai-sdk/openai";
import { createAnthropic } from "@ai-sdk/anthropic";

import { AiModelConfig } from "./config";
import { BunRuntime, BunContext } from "@effect/platform-bun";

export class AiError extends Data.TaggedError("AiError")<{msg: string}>{}
export class AiModel extends Effect.Service<AiModel>()(
    "AiModel",
    {
        effect: Effect.gen(function* () {
            const modelConfig = yield* AiModelConfig;
            // yield* modelConfig.saveConfig({"Anthropic": {"apiKey": "API_KEYSET", "authToken": "AUTH_TOKEN"}})
            const anthropicConfig = yield* modelConfig.forProvider("Anthropic");
            console.log("Anthropic Config:", anthropicConfig);
            let model;

            return {model} as const;
        })
    }
){}

const program = Effect.gen(function* () {
    const aiModel = yield* AiModel
}).pipe(
    Effect.provide(AiModel.Default),
    Effect.provide(AiModelConfig.Default)
)

BunRuntime.runMain(program.pipe(Effect.provide(BunContext.layer)))