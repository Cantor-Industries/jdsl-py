import { Effect, Layer } from "effect";

export class Router extends Effect.Service<Router>()(
    "Router",
    {
        effect: Effect.gen(function* () {
            const getConfig = () => "Router";

            return { getConfig } as const;
        })
    }
){}

export const RoundRobinRouter = Layer.effect(Router, Effect.gen(function* () {
    return Router.make({
    getConfig: () => "Round Robin Router"
})
}))

