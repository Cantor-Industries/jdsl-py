import ts from "typescript";
import fs from "node:fs";
import path from "node:path";

type VirtualFile = {
    version: number;
    content: string;
};

export class VirtualFS {
    private files = new Map<string, VirtualFile>();

    set(fileName: string, content: string) {
        const prev = this.files.get(fileName);
        this.files.set(normalize(fileName), {
            version: (prev?.version ?? 0) + 1,
            content,
        });
    }

    get(fileName: string) {
        return this.files.get(fileName);
    }

    has(fileName: string) {
        return this.files.has(fileName);
    }

    fileNames() {
        return [...this.files.keys()];
    }

    directoryExists(dir: string) {
        const prefix = dir.endsWith("/") ? dir : dir + "/";
        for (const key of this.files.keys()) {
            if (key.startsWith(prefix)) {
                return true;
            };
        }
        return false;
    }

    getDirectories(dir: string) {
        const prefix = dir.endsWith("/") ? dir : dir + "/";
        const dirs = new Set<string>();

        for (const key of this.files.keys()) {
            if (key.startsWith(prefix)) {
                const rest = key.slice(prefix.length);
                const part = rest.split("/")[0];
                if (part) dirs.add(part);
            }
        }

        return [...dirs];
    }

    getFiles() {
        return this.files;
    }

    writeFiles() {
        for (const [filename, content] of this.getFiles()) {
            fs.mkdirSync(path.dirname(filename), { recursive: true })
            fs.writeFileSync(filename, content.content, "utf-8")
        }
    }
}

export function createCompilerHost(
    fs: VirtualFS,
    options: ts.CompilerOptions
): ts.CompilerHost {
    const defaultHost = ts.createCompilerHost(options, true);

    return {
        ...defaultHost,

        fileExists: (fileName) => {
            const file = normalize(fileName);
            return fs.has(file) || defaultHost.fileExists(file)
        },

        readFile: (fileName) =>
            fs.get(normalize(fileName))?.content ?? defaultHost.readFile(normalize(fileName)),

        getSourceFile(fileName, languageVersion, onError) {
            const file = fs.get(normalize(fileName));
            if (file) {
                return ts.createSourceFile(
                    normalize(fileName),
                    file.content,
                    languageVersion,
                    true
                );
            }
            return defaultHost.getSourceFile(
                normalize(fileName),
                languageVersion,
                onError
            );
        },

        directoryExists: (dirName) =>
            fs.directoryExists(dirName) || defaultHost.directoryExists?.(dirName) || false,

        getDirectories: (path) =>
            [...fs.getDirectories(path), ...defaultHost.getDirectories?.(path) ?? []],

        realpath: (path) =>
            defaultHost.realpath?.(path) ?? path,

        getCurrentDirectory: () =>
            defaultHost.getCurrentDirectory(),

        writeFile(fileName, content) {
            fs.set(fileName, content);
        },
    };
}

export const normalize = (p: string) => ts.sys.resolvePath(p);

// const writeFiles = (vfs: VirtualFS) => {
//     for (const [filename, content] of vfs.getFiles()) {
//         // console.log(path.dirname(filename))
//         fs.mkdirSync(path.dirname(filename), { recursive: true })
//         fs.writeFileSync(filename, content.content, "utf-8")
//     }
// }

// const vfs = new VirtualFS();

// vfs.set(normalize('dist/src/root.ts'), `
// import { Context, Data, Effect, Either, Layer } from "effect";
// import { Status } from "./types.ts";
// import { TryThisAction, TryThisActionLive } from "./actions/TryThisAction.ts";
// const RootTag = Context.Tag("Root")<Root, Root.Behavior>();
// export class Root extends RootTag {
// }
// const RootErrorTag = (Data.TaggedError("RootError")<{
//     msg: string;
// }>);
// export class RootError extends RootErrorTag {
// }
// export declare namespace Root {
//     export interface Behavior {
//         status: Status;
//         update: () => Effect.Effect<Status, RootError, never>;
//     }
// }
// export const RootLive = Layer.effect(Root, Effect.gen(function* () {
//     const tryThisAction = yield* TryThisAction;
//     const proto = {
//         status: Status.READY,
//         update: () => Effect.gen(function* () {
//             const updateOrFail = yield* Effect.either(tryThisAction.update());
//             if (Either.isLeft(updateOrFail)) {
//                 console.log("Root Failed because:", updateOrFail.left.msg);
//                 proto.status = Status.FAILED;
//                 return proto.status;
//             }
//             else {
//                 proto.status = updateOrFail.right;
//                 return proto.status;
//             }
//         })
//     };
//     return proto;
// }));
// export const program = Effect.gen(function* () {
//     const root = yield* Root;
//     yield* root.update();
// }).pipe(Effect.provide(RootLive), Effect.provide(TryThisActionLive), Effect.runPromise);

// `);

// vfs.set(normalize('dist/src/actions/TryThisAction.ts'), `
// import { Context, Data, Effect, Layer } from "effect";
// import { Status } from "../types.ts";
// const TryThisActionTag = Context.Tag("TryThisAction")<TryThisAction, TryThisAction.Behavior>();
// export class TryThisAction extends TryThisActionTag {
// }
// const TryThisActionErrorTag = (Data.TaggedError("TryThisActionError")<{
//     msg: string;
// }>);
// export class TryThisActionError extends TryThisActionErrorTag {
// }
// export declare namespace TryThisAction {
//     export interface Behavior {
//         status: Status;
//         update: () => Effect.Effect<Status, TryThisActionError, never>;
//     }
// }
// export const TryThisActionLive = Layer.effect(TryThisAction, Effect.gen(function* () {
//     const proto = {
//         status: Status.FAILED,
//         run: (action: string, arg: string, age: number, save: boolean) => {
//             console.log("Agent Trying This");
//         },
//         update: () => Effect.gen(function* () {
//             try {
//                 proto.run("Play", "Hard", 12, true);
//                 return yield* Effect.succeed(proto.status);
//             }
//             catch (error: unknown) {
//                 if (error instanceof Error) {
//                     return yield* new TryThisActionError({ msg: error.message });
//                 }
//                 proto.status = Status.FAILED;
//                 return yield* new TryThisActionError({ msg: "Unknown Error has occured" });
//             }
//         })
//     };
//     return proto;
// }));


// `);

// vfs.set(normalize('dist/src/types.ts'), `
// export enum Status {
//     READY = "ready",
//     RUNNING = "running",
//     SUCCESS = "success",
//     FAILED = "failed"
// }
// `)

// console.log("Creating compiler options");
// const options: ts.CompilerOptions = {
//     target: ts.ScriptTarget.Latest,
//     module: ts.ModuleKind.NodeNext,
//     moduleResolution: ts.ModuleResolutionKind.NodeNext,
//     strict: true,
//     sourceMap: true,
//     esModuleInterop: true,
//     skipLibCheck: false,
// }

// console.log("Creating host");
// const host = createCompilerHost(vfs, options);

// console.log("Creating program");
// const program = ts.createProgram({
//     rootNames: ['dist/src/root.ts'],
//     options,
//     host,
// });

// // console.log("Emitting results");
// // const emitResult = program.emit();
// console.log("Checking diagnostics");
// // const diagnostics = ts.getPreEmitDiagnostics(program).concat(emitResult.diagnostics);
// const diagnostics = ts.getPreEmitDiagnostics(program).filter(diag => {
//     if (diag.code != 5097) return diag
// });

// if (diagnostics.length) {
//     throw new Error(
//         ts.formatDiagnosticsWithColorAndContext(diagnostics, {
//             getCanonicalFileName: f => f,
//             getCurrentDirectory: () => "/",
//             getNewLine: () => "\n"
//         })
//     );
// }

// writeFiles(vfs);
// // console.log(emitResult);
// console.log(vfs.fileNames());