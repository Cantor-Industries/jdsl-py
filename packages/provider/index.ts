import { Effect } from "effect";
import { createProviderRegistry, generateText } from "ai";
import { createGoogleGenerativeAI, google } from "@ai-sdk/google";
// google()
export class LanguageModel extends Effect.Service<LanguageModel>()(
    "LanguageModel",
    {
        effect: Effect.gen(function* () {

            const generateText = () => {

            }

            const streamText = () => {

            }

            return {generateText, streamText} as const
        })
    }
){}