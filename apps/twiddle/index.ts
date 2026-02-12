import { Effect } from "effect"
import { BunContext, BunRuntime } from "@effect/platform-bun"

import { createCliRenderer, Box, Text } from "@opentui/core"

const createRenderer = Effect.promise(async () => {
    const renderer = await createCliRenderer({
        exitOnCtrlC: true,
    })
    return renderer
})

const program = Effect.gen(function* () {

    const renderer = yield* createRenderer;
    renderer.root.add(
        Box(
            { borderStyle: "rounded", padding: 1, flexDirection: "column", gap: 1 },
            Text({ content: "Welcome", fg: "#FFFF00" }),
            Text({ content: "Press Ctrl+C to exit" }),
        ),
    )

})

BunRuntime.runMain(program.pipe(Effect.provide(BunContext.layer)))