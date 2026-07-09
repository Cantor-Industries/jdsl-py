import { Effect, Layer } from "effect";
import { type Config, type Providers } from "./config.ts";
import { type GenerateTextResponse, type LanguageModelError, LoadAPIKeyError } from "./types.ts";

export class Router extends Effect.Service<Router>()(
    "Router",
    {
        effect: Effect.gen(function* () {
            let config: Config;
            const getConfig = (provider: Providers) => Effect.gen(function* () {
                const cfg = config[provider];
                const apiKey = cfg?.apiKey[0];
                if (cfg && apiKey) {
                    return { ...cfg, apiKey: apiKey }
                } else {
                    return yield* new LoadAPIKeyError({ name: "LoadAPIKeyError", msg: `${provider} apiKey/auth is missing`, isRetryable: false });
                }
            });

            const initialize = (cfg: Config) => Effect.gen(function* () {
                config = cfg;
            });

            const tap = (e: Effect.Effect<GenerateTextResponse, LanguageModelError, never>) => Effect.tapErrorTag(e, "LoadAPIKeyError", (e) => Effect.succeed("ss"))

            return { getConfig, initialize, tap } as const;
        })
    }
) { }

export const RoundRobinRouter = Layer.effect(Router, Effect.gen(function* () {
    let config: Config;
    let index = 0;

    return Router.make({
        getConfig: (provider: Providers) => Effect.gen(function* () {
            const cfg = config[provider];
            const apiKey = cfg?.apiKey[index];
            if (cfg && apiKey) {
                return { ...cfg, apiKey: apiKey }
            } else {
                return yield* new LoadAPIKeyError({ name: "LoadAPIKeyError", msg: `${provider} apiKey/auth is missing`, isRetryable: false });
            }
        }),
        initialize: (cfg: Config) => Effect.gen(function* () {
            config = cfg;
        }),
        tap: (effect: Effect.Effect<GenerateTextResponse, LanguageModelError, never>) => Effect.tapErrorTag(
            effect,
            "InvalidApiKeyError",
            () => Effect.sync(() => { index += 1 })
        ).pipe(
            Effect.tapErrorTag("InsufficientBalanceError", () => Effect.sync(() => { index += 1 })),
            Effect.tapErrorTag("RateLimitError", () => Effect.sync(() => { index += 1 })),
        )
    })
}))

