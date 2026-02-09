import { Effect } from "effect";
import { createProviderRegistry, generateText as generateTextAi} from "ai";
import { createGoogleGenerativeAI, google } from "@ai-sdk/google";
import { AiModel } from "./src/models/aiModel.ts";
export class LanguageModel extends Effect.Service<LanguageModel>()(
    "LanguageModel",
    {
        effect: Effect.gen(function* () {
            const aiModel = yield* AiModel
            const generateText = (text: string) => Effect.promise(async () => {
                const response = await generateTextAi({
                    model: aiModel.model,
                    prompt: text
                })
                return response
            })

            const streamText = () => {

            }

            return {generateText, streamText} as const
        })
    }
){}