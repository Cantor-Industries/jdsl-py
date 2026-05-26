import { Effect } from "effect";
import { generateText as generateTextAiSdk, streamText as streamTextAiSdk } from "ai";
import { ContextWindow } from "src/context/context.ts";
import { AiModel } from "./src/aiModel.ts";

export class LanguageModel extends Effect.Service<LanguageModel>()(
    "LanguageModel",
    {
        effect: Effect.gen(function* () {
            const aiModel = yield* AiModel;
            const contextWindow = yield* ContextWindow;

            const generateText = (prompt: string) => Effect.gen(function* () {
                const model = yield* aiModel.getModel();
                contextWindow.push({message: {role: "user", content: prompt}});
                const window = yield* contextWindow.join();

                const fromAsync = () => Effect.tryPromise(async () => {
                    const response = await generateTextAiSdk({
                        model: model,
                        system: window.systemInstructions,
                        messages: window.messages,
                        maxRetries: 5,
                    })
                    return response
                })
                const {content, text, reasoning, reasoningText, finishReason, usage, totalUsage} = yield* fromAsync();
                yield* contextWindow.pop();
                return {content, text, reasoning, reasoningText, finishReason, usage, totalUsage};
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

            return { generateText, streamText } as const
        })
    }
) { }
