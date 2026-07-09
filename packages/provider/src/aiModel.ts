import { Effect } from "effect";
import type { UnknownException } from "effect/Cause";

import {
    APICallError as UnknownAPICallError,
    LoadAPIKeyError as UnknownLoadAPIKeyError,
    JSONParseError as UnknownJSONParseError,
    NoSuchModelError as UnknownNoSuchModelError,
    NoSuchProviderError as UnknownNoSuchProviderError,
    RetryError as UnknownRetryError,
} from "ai";
import { createGoogleGenerativeAI, type GoogleGenerativeAIProvider } from "@ai-sdk/google";
import { createOpenAI, type OpenAIProvider } from "@ai-sdk/openai";
import { createAnthropic, type AnthropicProvider } from "@ai-sdk/anthropic";
import { createDeepSeek, type DeepSeekProvider } from "@ai-sdk/deepseek";
import { createOpenAICompatible, type OpenAICompatibleProvider } from "@ai-sdk/openai-compatible";

import { APICallError, 
    InsufficientBalanceError, 
    InvalidApiKeyError, 
    JSONParseError, 
    LoadAPIKeyError, 
    ModelUnavailable, 
    NoSuchModelError, 
    NoSuchProviderError, 
    RateLimitError, 
    RetryError, 
    ServerError, 
    type GenerateTextResponse, 
    type StreamTextResponse 
} from "@jdsl/router/error";
import { AiModelConfig } from "@jdsl/router/config";

import { AiProvider } from "./providers.ts";

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
                const provider = yield* modelProvider.getProvider();
                const model = yield* modelProvider.getModelName();
                const config = yield* modelConfig.getConfig(provider);

                switch (provider) {
                    case "anthropic":
                        return createAnthropic({ apiKey: config.apiKey })(model);

                    case "deepseek":
                        return createDeepSeek({ apiKey: config.apiKey })(model);

                    case "google":
                        return createGoogleGenerativeAI({ apiKey: config.apiKey })(model);

                    case "nvidia":
                        return createOpenAICompatible({
                            baseURL: "https://integrate.api.nvidia.com/v1",
                            name: "nim",
                            headers: {
                                Authorization: `Bearer ${config.apiKey}`
                            }
                        })(model);

                    case "openai":
                        return createOpenAI({ apiKey: config.apiKey })(model);

                    case "zhipuai":
                        return createOpenAICompatible({
                            baseURL: "https://open.bigmodel.cn/api/paas/v4",
                            name: "zai-coding-plan",
                            apiKey: config.apiKey
                        })(model);

                    case "zai":
                        return createOpenAICompatible({
                            baseURL: "https://api.z.ai/api/paas/v4",
                            name: "zai-coding-plan",
                            apiKey: config.apiKey
                        })(model);

                    case "zai-coding-plan":
                        return createOpenAICompatible({
                            baseURL: "https://api.z.ai/api/coding/paas/v4",
                            name: "zai-coding-plan",
                            apiKey: config.apiKey
                        })(model);

                    case "zhipuai-coding-plan":
                        return createOpenAICompatible({
                            baseURL: "https://open.bigmodel.cn/api/coding/paas/v4",
                            name: "zai-coding-plan",
                            apiKey: config.apiKey
                        })(model);
                    default:
                        return yield* new NoSuchProviderError({ name: provider, msg: `${provider} not supported yet`, isRetryable: false });
                }
            });

            const mapGenerateTextError = (e: Effect.Effect<GenerateTextResponse, UnknownException, never>) => Effect.mapError(e, (e) => {
                if (UnknownAPICallError.isInstance(e.cause)) {
                    const cause = e.cause;
                    if (cause.statusCode === 400 || cause.statusCode === 401) {
                        return new InvalidApiKeyError({ name: "InvalidApiKeyError", msg: cause.message, isRetryable: cause.isRetryable });
                    } else if (cause.statusCode === 403) {
                        return new InsufficientBalanceError({ name: "InsufficientBalance", msg: cause.message, isRetryable: cause.isRetryable });
                    } else if (cause.statusCode === 429) {
                        return new RateLimitError({ name: "RateLimitError", msg: cause.message, isRetryable: cause.isRetryable });
                    } else if (cause.statusCode === 500) {
                        return new ServerError({ name: "ServerError", msg: cause.message, isRetryable: cause.isRetryable });
                    } else if (cause.statusCode === 503) {
                        return new ModelUnavailable({ name: "ModelUnavailable", msg: cause.message, isRetryable: cause.isRetryable });
                    }
                    return new APICallError({ name: "APICallError", msg: cause.message, isRetryable: cause.isRetryable });
                }
                if (UnknownLoadAPIKeyError.isInstance(e.cause)) {
                    return new LoadAPIKeyError({ name: "LoadAPIKeyError", msg: e.cause.message, isRetryable: false });
                }
                if (UnknownJSONParseError.isInstance(e.cause)) {
                    return new JSONParseError({ name: "JSONParseError", msg: e.cause.message, isRetryable: false });
                }
                if (UnknownNoSuchModelError.isInstance(e.cause)) {
                    return new NoSuchModelError({ name: "NoSuchModelError", msg: e.cause.message, isRetryable: false });
                }
                if (UnknownNoSuchProviderError.isInstance(e.cause)) {
                    return new NoSuchProviderError({ name: "NoSuchProviderError", msg: e.cause.message, isRetryable: false });
                }
                if (UnknownRetryError.isInstance(e.cause)) {
                    return new RetryError({ name: "RetryError", msg: e.cause.message, isRetryable: false });
                }

                return new InvalidApiKeyError({ name: "UnkownCertificateError", msg: "Forbidden Resource, Authorization Failed", isRetryable: false });
            })

            return { getModel, mapGenerateTextError } as const;
        })
    }
) { }

