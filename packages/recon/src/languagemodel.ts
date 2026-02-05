import { Context, type Effect} from "effect";

const LanguageModelTag = Context.Tag("AiLanguageModel")<LanguageModel, LanguageModel.LanguageModel>();
export class LanguageModel extends LanguageModelTag {};

export declare namespace LanguageModel {
    export interface LanguageModel {
        generateText: (text: string) => Effect.Effect<AiResponse.AiResponse, never, never>;
        
        // streamText: () => void;
        // generateObject: () => void;
    }
}

export declare namespace AiResponse {
    export interface AiResponse {
        readonly response: string;
        readonly meta: Metadata;
    }

    export interface Metadata {
        readonly inputTokens: number;
        readonly outputTokens: number;
    }
}
