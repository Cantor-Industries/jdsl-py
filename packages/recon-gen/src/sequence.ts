import { Context, Data, Effect } from "effect"
import { Tool, Skill } from "./types.ts";

const tools1 = {
    first: (w: string) => console.log(w),
    second: (w: string) => Effect.succeed(12)
} satisfies Tool

export const definition = {
    type: "root",
    child: {
        type: "sequence",
        children: [
            {
                type: "action",
                call: "first",
                args: ["hello world"]
            },
            {
                type: "action",
                call: "first",
                args: ["how do you spell chleramus"]
            }
        ]
    }
} satisfies Skill<typeof tools1 >

const First = (w: string) => Effect.sync(() => {
    console.log(w);
    return w;
})

const Second = (w: string) => Effect.succeed(12);
const map = (n: number) => Effect.succeed(n.toString());

const sequence = Effect.succeed("Hello World").pipe(
    Effect.flatMap(First),
    Effect.flatMap(Second),
    Effect.flatMap(map),
    Effect.flatMap(First),
    Effect.runPromise
)