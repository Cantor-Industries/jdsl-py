import { Data, Effect } from "effect";
import { generateText as generateTextAiSdk, streamText as streamTextAiSdk } from "ai";
import { ContextWindow } from "./src/context/context.ts";
import { AiModel } from "./src/aiModel.ts";
import { AiProvider } from "./src/providers.ts";
import { mapLanguageModelError } from "./src/types.ts";

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
                // TO-DO: Add cause property
                const fromAsync = () => Effect.tryPromise(async () => {
                    const response = await generateTextAiSdk({
                        model: model,
                        system: window.systemInstructions,
                        messages: window.messages,
                        maxRetries: 5,
                    })
                    const { content, text, reasoning, reasoningText, finishReason, usage, totalUsage } = response;
                    return { content, text, reasoning, reasoningText, finishReason, usage, totalUsage }
                })
                const result = fromAsync();
                yield* contextWindow.pop();
                return yield* mapLanguageModelError(result);
            })

            const streamText = (text: string) => Effect.gen(function* () {
                const model = yield* aiModel.getModel();

                const fromAsync = (prompt: string) => Effect.tryPromise(async () => {
                    const response = await streamTextAiSdk({
                        model: model,
                        prompt: prompt,
                        maxRetries: 5
                    })
                    return response
                })
                const { textStream } = yield* fromAsync(text);
                const reader = textStream.getReader();
                return yield* fromAsync(text)
            })

            const chooseProvider = provider.chooseProvider;
            const chooseModel = provider.chooseModel;

            return { generateText, streamText, chooseModel, chooseProvider } as const
        }),
    }
) { }
