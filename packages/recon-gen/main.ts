#!/usr/bin/env tsx
import ts from "typescript";
import process from "node:process";
import path, { basename } from "node:path";
import fs from "node:fs";

import { Effect, } from "effect";
import { NodeContext, NodeRuntime } from "@effect/platform-node"
import { Tools, Transform } from "./src/transform.ts";
import { EntryFileMissingError, PackageJsonError } from "./src/errors.ts";
import { DenoJson, PackageJson, Skill, Tool } from "./src/types.ts";
import { VFS } from "./src/vfs.ts";
import { ReconLanguageServer } from "./src/lsp.ts";
export { run } from "./src/types.ts";
export type { Action, Selector, Sequence, Skill, Tool } from "./src/types.ts";

function resolveExports(exportsField: unknown): string | undefined {
    if (typeof exportsField === "string") {
        return exportsField;
    }

    if (typeof exportsField !== "object" || exportsField === null) {
        return undefined;
    }

    const exportsObj = exportsField as Record<string, unknown>;

    // Prefer "." if present
    const root = exportsObj["."] ?? Object.values(exportsObj)[0];
    if (!root) return undefined;

    if (typeof root === "string") {
        return root;
    }

    if (typeof root === "object" && root !== null) {
        const conditions = root as Record<string, unknown>;

        return (
            (typeof conditions.import === "string" && conditions.import) ||
            (typeof conditions.require === "string" && conditions.require) ||
            (typeof conditions.default === "string" && conditions.default) ||
            undefined
        );
    }

    return undefined;
}

const checkTsProject = Effect.gen(function* () {
    const cwd = process.cwd();
    const packageJsonPath = path.resolve(cwd, "package.json");
    const denoJsonPath = path.resolve(cwd, "deno.json");
    if (fs.existsSync(packageJsonPath)) {
        return packageJsonPath;
    } else if (fs.existsSync(denoJsonPath)) {
        return denoJsonPath;
    } else {
        return yield* new PackageJsonError({ msg: "Could not read package/deno.json: Error: ENOENT: no such file or directory" })
    }
})

const getEntryFile = (jsonFilePath: string) => Effect.gen(function* () {
    const jsonFile = fs.readFileSync(jsonFilePath, "utf-8");

    // Minimal JSONC support for deno.jsonc
    const cleaned =
        jsonFilePath.endsWith(".jsonc")
            ? jsonFile.replace(/\/\/.*|\/\*[\s\S]*?\*\//g, "")
            : jsonFile;

    const data = JSON.parse(cleaned);
    const file = path.basename(jsonFilePath);

    if (file === "package.json") { // ---------- NODE ----------
        const pkg = data as PackageJson;

        if (pkg.main) {
            return pkg.main;
        }

        const fromExports = resolveExports(pkg.exports);
        if (fromExports) {
            return fromExports;
        }

        // return "index.ts";
    } else if (file === "deno.json" || file === "deno.jsonc") {   // ---------- DENO ----------
        const deno = data as DenoJson;

        const fromExports = resolveExports(deno.exports);
        if (fromExports) {
            return fromExports;
        }
        return yield* new EntryFileMissingError({ msg: "Deno project detected but no exports entry point found" })
    }
    return yield* new EntryFileMissingError({ msg: `Unsupported config file: ${jsonFilePath}` })
})

const getAST = (entryFile: string) => Effect.gen(function* () {
    const fullPath = path.resolve(process.cwd(), entryFile);
    if (!fs.existsSync(fullPath)) {
        return yield* new EntryFileMissingError({ msg: `Entry file ${basename(fullPath)} could not be found` });
    }
    const rawFile = fs.readFileSync(fullPath, 'utf-8');
    return ts.createSourceFile(basename(fullPath), rawFile, ts.ScriptTarget.ESNext, true, ts.ScriptKind.TS);
})

export const definition = {
    "type": "root",
    "child": {
        "type": "action",
        "call": "last",
        "args": ["hello maties!"]
    }
} satisfies Skill

export const tools = {
    last: (w: string) => console.log(w)
} satisfies Tool

const main = Effect.gen(function* () {
    const jsonFilePath = yield* checkTsProject;
    const entryFile = yield* getEntryFile(jsonFilePath);
    const ast = yield* getAST(entryFile);
    const transform = yield* Transform;
    yield* transform(ast);
}).pipe(
    Effect.provide(Transform.Default),
    Effect.provide(ReconLanguageServer.Default),
    Effect.provide(VFS.Default),
    Effect.provide(Tools.Default),
)

NodeRuntime.runMain(
    main.pipe(
        Effect.provide(NodeContext.layer)
    )
);
