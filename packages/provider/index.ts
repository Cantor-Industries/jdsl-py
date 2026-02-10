import { Effect } from "effect";
import { generateText as generateTextAi } from "ai";
import { BunRuntime, BunContext } from "@effect/platform-bun";

import { AiModel } from "./src/aiModel.ts";
import { ModelsDev } from "./src/models/models-dev.ts";
import { AiModelConfig } from "./src/config.ts";
import { AiProvider } from "./src/providers.ts";

export class LanguageModel extends Effect.Service<LanguageModel>()(
    "LanguageModel",
    {
        effect: Effect.gen(function* () {
            const aiModel = yield* AiModel;

            const generateText = (text: string) => Effect.gen(function* () {
                const model = yield* aiModel.getModel();

                const fromAsync = (prompt: string) => Effect.tryPromise(async () => {
                    const response = await generateTextAi({
                        model: model,
                        prompt: prompt
                    })
                    return response
                })

                return yield* fromAsync(text)
            })

            const streamText = () => {

            }

            return { generateText, streamText } as const
        })
    }
) { }

const program = Effect.gen(function* () {
    const languageModel = yield* LanguageModel;
    const modelProvider = yield* AiProvider;

    yield* modelProvider.chooseProvider("google");
    yield* modelProvider.chooseModel("gemini-2.0-flash");
    const response = yield* languageModel.generateText("Who released the song What is love and in what year as part of what album. Respond in less than 20 words");
    console.log(response.text)
}).pipe(
    Effect.provide(LanguageModel.Default),
    Effect.provide(AiModel.Default),
    Effect.provide(AiModelConfig.Default),
    Effect.provide(AiProvider.Default),
    Effect.provide(ModelsDev.Default)
)

BunRuntime.runMain(program.pipe(Effect.provide(BunContext.layer)))