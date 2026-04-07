import { Effect } from "effect";

export interface Content {
    type: "text" | "image",
    text: string
};

export interface Message {
    role: "user" | "assistant" | "system";
    content: string | Content[]
};

export interface Context {
    system?: string ;
    message?: Message;
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
                const messages: Message[] = []
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