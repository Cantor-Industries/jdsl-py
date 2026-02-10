import { Data, Effect } from "effect";

import { createGoogleGenerativeAI, type GoogleGenerativeAIProvider } from "@ai-sdk/google";
import { createOpenAI, type OpenAIProvider } from "@ai-sdk/openai";
import { createAnthropic, type AnthropicProvider } from "@ai-sdk/anthropic";

import { AiModelConfig } from "./config";
import { AiProvider } from "./providers";

export class AiError extends Data.TaggedError("AiError")<{msg: string}>{};
export type AiModelProvider = AnthropicProvider | GoogleGenerativeAIProvider | OpenAIProvider;

export class AiModel extends Effect.Service<AiModel>()(
    "AiModel",
    {
        effect: Effect.gen(function* () {
            const modelConfig = yield* AiModelConfig;
            const modelProvider = yield* AiProvider;

            yield* modelProvider.chooseProvider("google");
            yield* modelProvider.chooseModel("gemini-2.0-flash");

            const getModel = () => Effect.gen(function*() {
                const config = yield* modelConfig.getConfig();
                const provider = yield* modelProvider.getProvider();

                switch (provider) {
                    case "anthropic":
                        return createAnthropic(config)(yield* modelProvider.getModelName());

                    case "google":
                        return createGoogleGenerativeAI(config) (yield* modelProvider.getModelName());

                    case "openai":
                        return createOpenAI(config) (yield* modelProvider.getModelName());

                    default:
                        return yield* new AiError({msg: `${provider} not supported yet`});
                }
            });
            
            return {getModel} as const;
        })
    }
){}

