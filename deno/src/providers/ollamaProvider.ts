import { Context, Effect, Layer } from "effect";
import { LanguageModel, type AiResponse } from "../languagemodel.ts";
import { Ollama } from "ollama";

const OllamaClientTag = Context.Tag("OllamaClient")<OllamaClient, OllamaClient.OllamaClient>()
export class OllamaClient extends OllamaClientTag {};

export declare namespace OllamaClient {
    export interface OllamaClient {
        apiKey: string;
        model: string;
    }
}

export const OllamaProvider = Layer.effect(LanguageModel, Effect.gen(function* () {
    const ollamaClient = yield* OllamaClient;

    const proto = {
        generateText: (text: string) => Effect.promise(async function () {
            const ollama = new Ollama();
            const response = await ollama.chat({
                model: ollamaClient.model,
                messages: [{role: "system", content: "You are a teacher who explains everything concisely and accurately"},{role: "user", content: text}],
                stream: false,
                keep_alive: "10m",
                options: {
                    // temperature: 0.5,
                    // seed: 10100,
                    num_ctx:8192
                }
            })
            const result: AiResponse.AiResponse = {
                response: response.message.content,
                meta: {inputTokens: response.prompt_eval_count, outputTokens: response.eval_count}
            }
            return result
        }),
        generateObject: (text: string) => Effect.promise(async function () {
            const ollama = new Ollama();
            const response = await ollama.generate({
                model: ollamaClient.model,
                prompt: text,
                format: "json",
                
            })
            response.response
        })
    }
    return proto;
}))

