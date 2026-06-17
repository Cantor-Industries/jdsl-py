import { Data, Effect } from "effect";

import { createGoogleGenerativeAI, type GoogleGenerativeAIProvider } from "@ai-sdk/google";
import { createOpenAI, type OpenAIProvider } from "@ai-sdk/openai";
import { createAnthropic, type AnthropicProvider } from "@ai-sdk/anthropic";
import { createDeepSeek, type DeepSeekProvider } from "@ai-sdk/deepseek";
import { createOpenAICompatible, type OpenAICompatibleProvider } from "@ai-sdk/openai-compatible";

import { AiModelConfig } from "./config.ts";
import { AiProvider } from "./providers.ts";

export class AiError extends Data.TaggedError("AiError")<{ msg: string }> { };
export type AiModelProvider =
    AnthropicProvider |
    DeepSeekProvider |
    GoogleGenerativeAIProvider |
    OpenAIProvider |
    OpenAICompatibleProvider;

export class AiModel extends Effect.Service<AiModel>()(
    "AiModel",
    {
        effect: Effect.gen(function* () {
            const modelConfig = yield* AiModelConfig;
            const modelProvider = yield* AiProvider;

            const getModel = () => Effect.gen(function* () {
                const config = yield* modelConfig.getConfig();
                const provider = yield* modelProvider.getProvider();
                const model = yield* modelProvider.getModelName();

                switch (provider) {
                    case "anthropic":
                        return createAnthropic(config)(model);

                    case "deepseek":
                        return createDeepSeek(config)(model);

                    case "google":
                        return createGoogleGenerativeAI(config)(model);

                    case "nvidia":
                        return createOpenAICompatible({
                            baseURL: "https://integrate.api.nvidia.com/v1", 
                            name: "nim",
                            headers: {
                                Authorization: `Bearer ${config.apiKey}`
                            }
                        })(model);

                    case "openai":
                        return createOpenAI(config)(model);

                    default:
                        return yield* new AiError({ msg: `${provider} not supported yet` });
                }
            });

            return { getModel } as const;
        })
    }
) { }

