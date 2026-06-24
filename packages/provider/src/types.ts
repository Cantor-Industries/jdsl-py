import { Data, Effect } from "effect";
import type { UnknownException } from "effect/Cause";

import {
    APICallError as UnknownAPICallError,
    LoadAPIKeyError as UnknownLoadAPIKeyError,
    JSONParseError as UnknownJSONParseError,
    NoSuchModelError as UnknownNoSuchModelError,
    NoSuchProviderError as UnknownNoSuchProviderError,
    RetryError as UnknownRetryError,
    type ContentPart,
    type FinishReason,
    type LanguageModelUsage,
    type ReasoningOutput,
    type ToolSet
} from "ai";

export interface GenerateTextResponse {
    content: ContentPart<ToolSet>[];
    text: string;
    reasoning: ReasoningOutput[];
    reasoningText: string | undefined;
    finishReason: FinishReason;
    usage: LanguageModelUsage;
    totalUsage: LanguageModelUsage;
}

export interface StreamTextResponse {
    content: PromiseLike<ContentPart<ToolSet>[]>;
    text: PromiseLike<string>;
    textStream: AsyncIterable<string>;
    reasoning: PromiseLike<ReasoningOutput[]>;
    reasoningText: PromiseLike<string | undefined>;
    finishReason: PromiseLike<FinishReason>;
    usage: PromiseLike<LanguageModelUsage>;
    totalUsage: PromiseLike<LanguageModelUsage>;
}

export interface AiError {
    name: string;
    msg: string;
    isRetryable: boolean;
}

export class APICallError extends Data.TaggedError("ApiCallError")<AiError> { }
export class LoadAPIKeyError extends Data.TaggedError("LoadAPIKeyError")<AiError> { }
export class JSONParseError extends Data.TaggedError("JSONParseError")<AiError> { }
export class NoSuchModelError extends Data.TaggedError("NoSuchModelError")<AiError> { }
export class NoSuchProviderError extends Data.TaggedError("NoSuchProviderError")<AiError> { }
export class RetryError extends Data.TaggedError("RetryError")<AiError> { }

export const mapLanguageModelError = (e: Effect.Effect<GenerateTextResponse | StreamTextResponse, UnknownException, never>) => Effect.mapError(e, (e) => {
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
    if (UnknownAPICallError.isInstance(e.cause)) {
        return new APICallError({ name: "APICallError", msg: e.cause.message, isRetryable: e.cause.isRetryable });
    }
    return new APICallError({ name: "ApiCallError", msg: "Forbidden Resource, Authorization Failed", isRetryable: false });
})