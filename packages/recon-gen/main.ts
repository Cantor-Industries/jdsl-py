#!/usr/bin/env tsx
import { Effect, } from "effect";
import { NodeContext, NodeRuntime } from "@effect/platform-node"
import { Tools, Transform } from "./src/transform.ts";
import { Skill, Tool } from "./src/types.ts";
import { VFS } from "./src/vfs.ts";
import { ReconLanguageServer } from "./src/lsp.ts";
import { ReconEnvBuilder } from "./src/env.ts";
import { ReconInitializer } from "./src/initializer.ts";
export type { Action, Selector, Sequence, Skill, Tool } from "./src/types.ts";


const tools = {
    first: (f: number) => f,
    second: (s: number) => s,
    last: (l: number) => l,
} satisfies Tool

export const definition = {
    type: "root",
    child: {
        type: "sequence",
        children: [
            {
                type: "selector",
                children: [
                    {
                        type: "action",
                        call: "first",
                        args: [144]
                    },
                    {
                        type: "action",
                        call: "second",
                        // args: [124]
                    },
                ]
            },
            {
                type: "action",
                call: "last",
                // args: [112]
            }
        ]
    }
} satisfies Skill<typeof tools>

const main = Effect.gen(function* () {
    yield* ReconInitializer.init
}).pipe(
    Effect.provide(ReconInitializer.Default),
    Effect.provide(Transform.Default),
    Effect.provide(ReconEnvBuilder.Default),
    Effect.provide(ReconLanguageServer.Default),
    Effect.provide(VFS.Default),
    Effect.provide(Tools.Default),
)

NodeRuntime.runMain(
    main.pipe(
        Effect.provide(NodeContext.layer)
    )
);
