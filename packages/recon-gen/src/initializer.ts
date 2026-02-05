import path, { basename } from "node:path";
import fs from "node:fs";
import process from "node:process";

import { Effect } from "effect";
import { PackageJsonError, EntryFileMissingError } from "./errors.ts";
import { ReconLanguageServer } from "./lsp.ts";
import { PackageJson, DenoJson } from "./types.ts";
import { VFS } from "./vfs.ts";
import { Transform } from "./transform.ts";

export class ReconInitializer extends Effect.Service<ReconInitializer>()(
    "ReconInitializer",
    {
        accessors: true,
        effect: Effect.gen(function* () {
            const languageServer = yield* ReconLanguageServer;
            const vfs = yield* VFS;
            const transform = yield* Transform;

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

                if (file === "package.json") {
                    const pkg = data as PackageJson;

                    if (pkg.main) {
                        return pkg.main;
                    }

                    const fromExports = resolveExports(pkg.exports);
                    if (fromExports) {
                        return fromExports;
                    }

                } else if (file === "deno.json" || file === "deno.jsonc") {
                    const deno = data as DenoJson;

                    const fromExports = resolveExports(deno.exports);
                    if (fromExports) {
                        return fromExports;
                    }
                    return yield* new EntryFileMissingError({ msg: "Deno project detected but no exports entry point found" })
                }
                return yield* new EntryFileMissingError({ msg: `Unsupported config file: ${jsonFilePath}` })
            })
            const init = Effect.gen(function* () {
                const jsonFilePath = yield* checkTsProject;
                const entryFile = yield* getEntryFile(jsonFilePath);

                const fullPath = path.resolve(process.cwd(), entryFile);
                if (!fs.existsSync(fullPath)) {
                    return yield* new EntryFileMissingError({ msg: `Entry file ${basename(fullPath)} could not be found` });
                }
                const rawFile = fs.readFileSync(fullPath, 'utf-8');
                vfs.set(fullPath, rawFile);
                languageServer.getSyntacticDiagnostics(fullPath);
                const program = languageServer.getProgram();
                const sourceFile = program?.getSourceFile(fullPath)
                yield* transform(sourceFile!)
            })
            return {init} as const
        }),
    }
) { }
