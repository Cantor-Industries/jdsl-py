import { Effect, Layer } from "effect";
import { LanguageModel } from "./src/languagemodel.ts";
import { OllamaClient, OllamaProvider } from "./src/providers/ollamaProvider.ts";

export const gemma3270m = Layer.effect(OllamaClient, Effect.sync(() => {
    return {
        model: "gemma3:1b",
        apiKey: "Your Api Key Goes Here"
    }
}))

const program = Effect.gen(function* () {
    const aiModel = yield* LanguageModel;

    const response = yield* aiModel.generateText("Where does the sun go at night?");
    console.log(response);
});

const runnable = program.pipe(Effect.provide(OllamaProvider), Effect.provide(gemma3270m));
Effect.runPromise(runnable);

