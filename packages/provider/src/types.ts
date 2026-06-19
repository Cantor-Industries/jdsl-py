import { Data, Effect } from "effect";
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

export interface AiError {
    name: string;
    msg: string
}

export class APICallError extends Data.TaggedError("ApiCallError")<AiError> { }
export class LoadAPIKeyError extends Data.TaggedError("LoadAPIKeyError")<AiError> { }
export class JSONParseError extends Data.TaggedError("JSONParseError")<AiError> { }
export class NoSuchModelError extends Data.TaggedError("NoSuchModelError")<AiError> { }
export class NoSuchProviderError extends Data.TaggedError("NoSuchProviderError")<AiError> { }
export class RetryError extends Data.TaggedError("RetryError")<AiError> { }

export const mapLanguageModelError = (e: Effect.Effect<GenerateTextResponse, unknown, never>) => Effect.mapError(e, (e) => {
    if (UnknownAPICallError.isInstance(e)) {
        return new APICallError({ name: e.name, msg: e.message });
    }
    if (UnknownLoadAPIKeyError.isInstance(e)) {
        return new LoadAPIKeyError({ name: e.name, msg: e.message });
    }
    if (UnknownJSONParseError.isInstance(e)) {
        return new JSONParseError({ name: e.name, msg: e.message });
    }
    if (UnknownNoSuchModelError.isInstance(e)) {
        return new NoSuchModelError({ name: e.name, msg: e.message });
    }
    if (UnknownNoSuchProviderError.isInstance(e)) {
        return new NoSuchProviderError({ name: e.name, msg: e.message });
    }
    if (UnknownRetryError.isInstance(e)) {
        return new RetryError({ name: e.name, msg: e.message });
    }
    return new APICallError({ name: "apiError", msg: "LanguageModel failed with unknown error" });
})