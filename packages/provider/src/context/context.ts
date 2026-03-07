import { Effect } from "effect";

export interface Content {
    type: "text" | "image",
    text: string
}

export interface Message {
    role: "user" | "assistant" | "system";
    content: Content[]
}

export class ContextWindow extends Effect.Service<ContextWindow>()(
    "ContextWindow",
    {
        effect: Effect.gen(function* () {
            const systemInstructions: string[] = [];
            const messages: Message[] = []

            const addSystemInstruction = (instruction: string) => Effect.sync(() => systemInstructions.push(instruction));
            const addMessage = (message: Message) => Effect.sync(() => messages.push(message));

            const join = () => Effect.sync(() => {
                const system = systemInstructions.join("\n");
                return {systemInstructions: system, messages: messages};
            })
            return { addSystemInstruction, addMessage, join } as const;
        })
    }
) { }