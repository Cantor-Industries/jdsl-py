import ts from "typescript";
import process from "node:process";
import path, { basename } from "node:path";
import fs from "node:fs";

import { Effect } from "effect";
import { NodeContext, NodeRuntime } from "@effect/platform-node"
import { transform } from "./src/parser.ts";
import { EntryFileMissingError, PackageJsonError } from "./src/errors.ts";
import { DenoJson, PackageJson, Tool, Skill } from "./src/types.ts";

const agent = {
    TryThis: (action: string, arg: string, age: number ) => {
        //this might be forgotten
        console.log("Running This from Skill Tree");
    }
} satisfies Tool

const tree = {
    type: "root",
    child: {    
        type: "action",
        call: "TryThis",
        args: ["Play", "Hard", 12] 
    }
} satisfies Skill<typeof agent>


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
        return yield* new EntryFileMissingError({msg: "Deno project detected but no exports entry point found"})
    }
    return yield* new EntryFileMissingError({msg: `Unsupported config file: ${jsonFilePath}`})
    // console.log(jsonFile);
})

const getAST = (entryFile: string) => Effect.gen(function* () {
    const fullPath = path.resolve(process.cwd(), entryFile);
    if (!fs.existsSync(fullPath)) {
        return yield* new EntryFileMissingError({msg: `Entry file ${basename(fullPath)} could not be found`});
    }
    const rawFile = fs.readFileSync(fullPath, 'utf-8');
    return ts.createSourceFile(basename(fullPath), rawFile, ts.ScriptTarget.ESNext, true, ts.ScriptKind.TS);
})

const main = Effect.gen(function* () {
    const jsonFilePath = yield* checkTsProject;
    const entryFile = yield* getEntryFile(jsonFilePath);
    const ast = yield* getAST(entryFile);
    console.log(ast.fileName);
    const vfs = yield* transform(ast);
    vfs.writeFiles();
})

/**
 * Algorithm for Recon Codegen
 * 1. Check if package.json or deno.json exists in the project
 *  - If neither exists -> throw Not Node Project Error
 * 2. Read the main entry file in package.json
 *  - If missing, read alternative entry files or throw Missing Entry File
 * 3. Extract the path to the main entry file and check if file exists
 *  - If missing, throw file missing error
 * 4. Read the entry file as a string and create a sourcefile
 * 5. Parse the sourcefile looking for satisfies keyword
 *  - for each export keyword:
 *      - Extract its type declaration,
 *      - Check if it's assignable to either tree or agent interfaces
 *  - if no tree is found, throw a no behavior tree found
 */

NodeRuntime.runMain(main.pipe(Effect.provide(NodeContext.layer)));