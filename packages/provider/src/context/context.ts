import { Effect } from "effect";
import { type ModelMessage } from "ai";

export interface Context {
    system?: string ;
    message?: ModelMessage;
};

export class ContextWindow extends Effect.Service<ContextWindow>()(
    "ContextWindow",
    {
        effect: Effect.gen(function* () {
            const window: Context[] = [];

            const push = (context: Context) => Effect.sync(() => window.push(context));
            const pop = () => Effect.sync(() => window.pop());

            const join = () => Effect.sync(() => {
                const system: string[] = []
                const messages: ModelMessage[] = []
                window.forEach(value => {
                    if (value.system) system.push(value.system);
                    if (value.message) messages.push(value.message)
                })
                return {systemInstructions: system.join("\n"), messages: messages};
            })
            return { join, push, pop } as const;
        })
    }
) { }