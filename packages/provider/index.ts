import { Data, Effect } from "effect";
import { generateText as generateTextAiSdk, streamText as streamTextAiSdk } from "ai";
import { ContextWindow } from "./src/context/context.ts";
import { AiModel } from "./src/aiModel.ts";
import { AiProvider } from "./src/providers.ts";
import { mapLanguageModelError } from "../router/src/types.ts";

export class LanguageModelError extends Data.TaggedError("LanguageModelError")<{ msg: string }> { }
export class LanguageModel extends Effect.Service<LanguageModel>()(
    "LanguageModel",
    {
        effect: Effect.gen(function* () {
            const aiModel = yield* AiModel;
            const contextWindow = yield* ContextWindow;
            const provider = yield* AiProvider;

            const generateText = (prompt: string) => Effect.gen(function* () {
                const model = yield* aiModel.getModel();
                contextWindow.push({ message: { role: "user", content: prompt } });
                const window = yield* contextWindow.join();
                window.messages.push({ role: "user", content: prompt })

                const fromAsync = () => Effect.tryPromise(async () => {
                    const response = await generateTextAiSdk({
                        model: model,
                        system: window.systemInstructions,
                        messages: window.messages,
                        maxRetries: 0,
                    })
                    return response;
                }).pipe(
                    Effect.map((response) => {
                        const { content, text, reasoning, reasoningText, finishReason, usage, totalUsage } = response;
                        return { content, text, reasoning, reasoningText, finishReason, usage, totalUsage } 
                    }),
                    mapLanguageModelError
                )
                const result = yield* fromAsync();
                yield* contextWindow.pop();
                return result;
            })

            const streamText = (prompt: string) => Effect.gen(function* () {
                const model = yield* aiModel.getModel();
                contextWindow.push({ message: { role: "user", content: prompt } });
                const window = yield* contextWindow.join();
                window.messages.push({ role: "user", content: prompt })
                // TO-DO: Add cause property
                const fromAsync = () => Effect.tryPromise(async () => {
                    const response = await streamTextAiSdk({
                        model: model,
                        system: window.systemInstructions,
                        prompt: window.messages,
                        maxRetries: 0
                    })
                    return response;
                }).pipe(
                    Effect.map((response) => {
                        const { content, text, textStream, reasoning, reasoningText, finishReason, usage, totalUsage } = response;
                        return { content, text, textStream, reasoning, reasoningText, finishReason, usage, totalUsage } 
                    }),
                    mapLanguageModelError
                )
                const result = yield* fromAsync();
                yield* contextWindow.pop();
                return result;
            })

            const chooseProvider = provider.chooseProvider;
            const chooseModel = provider.chooseModel;

            return { generateText, streamText, chooseModel, chooseProvider } as const
        }),
    }
) { }
