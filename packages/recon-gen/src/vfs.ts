import ts from "typescript";
import fs from "node:fs";
import path from "node:path";
import { Effect } from "effect";

type VirtualFile = {
    version: number;
    content: string;
};

export class VFS extends Effect.Service<VFS>()(
    "VirtualFS",
    {
        effect: Effect.sync(() => {
            console.log("VFS INIT")            
            const files = new Map<string, VirtualFile>();
            const proto = {
                set(fileName: string, content: string) {
                    const prev = files.get(fileName);
                    files.set(normalize(fileName), {
                        version: (prev?.version ?? 0) + 1,
                        content,
                    });
                },
                get(fileName: string) {
                    return files.get(fileName);
                },
                has(fileName: string) {
                    return files.has(fileName);
                },
                fileNames() {
                    return [...files.keys()];
                },
                directoryExists(dir: string) {
                    const prefix = dir.endsWith("/") ? dir : dir + "/";
                    for (const key of files.keys()) {
                        if (key.startsWith(prefix)) {
                            return true;
                        };
                    }
                    return false;
                },
                getDirectories(dir: string) {
                    const prefix = dir.endsWith("/") ? dir : dir + "/";
                    const dirs = new Set<string>();

                    for (const key of files.keys()) {
                        if (key.startsWith(prefix)) {
                            const rest = key.slice(prefix.length);
                            const part = rest.split("/")[0];
                            if (part) dirs.add(part);
                        }
                    }

                    return [...dirs];
                },
                getFiles() {
                    return files;
                },
                writeFiles() {
                    for (const [filename, content] of proto.getFiles()) {
                        fs.mkdirSync(path.dirname(filename), { recursive: true })
                        fs.writeFileSync(filename, content.content, "utf-8")
                    }
                }
            }

            proto.set(normalize('dist/src/types.ts'),
                `export enum Status {
                READY = "ready",
                RUNNING = "running",
                SUCCESS = "success",
                FAILED = "failed"
            }
            `)
            return proto;
        })
    }
) { }

// export class VirtualFS {
//     private files = new Map<string, VirtualFile>();

//     set(fileName: string, content: string) {
//         const prev = this.files.get(fileName);
//         this.files.set(normalize(fileName), {
//             version: (prev?.version ?? 0) + 1,
//             content,
//         });
//     }

//     get(fileName: string) {
//         return this.files.get(fileName);
//     }

//     has(fileName: string) {
//         return this.files.has(fileName);
//     }

//     fileNames() {
//         return [...this.files.keys()];
//     }

//     directoryExists(dir: string) {
//         const prefix = dir.endsWith("/") ? dir : dir + "/";
//         for (const key of this.files.keys()) {
//             if (key.startsWith(prefix)) {
//                 return true;
//             };
//         }
//         return false;
//     }

//     getDirectories(dir: string) {
//         const prefix = dir.endsWith("/") ? dir : dir + "/";
//         const dirs = new Set<string>();

//         for (const key of this.files.keys()) {
//             if (key.startsWith(prefix)) {
//                 const rest = key.slice(prefix.length);
//                 const part = rest.split("/")[0];
//                 if (part) dirs.add(part);
//             }
//         }

//         return [...dirs];
//     }

//     getFiles() {
//         return this.files;
//     }

//     writeFiles() {
//         for (const [filename, content] of this.getFiles()) {
//             fs.mkdirSync(path.dirname(filename), { recursive: true })
//             fs.writeFileSync(filename, content.content, "utf-8")
//         }
//     }
// }

// export function createCompilerHost(
//     fs: VirtualFS,
//     options: ts.CompilerOptions
// ): ts.CompilerHost {
//     const defaultHost = ts.createCompilerHost(options, true);

//     return {
//         ...defaultHost,

//         fileExists: (fileName) => {
//             const file = normalize(fileName);
//             return fs.has(file) || defaultHost.fileExists(file)
//         },

//         readFile: (fileName) =>
//             fs.get(normalize(fileName))?.content ?? defaultHost.readFile(normalize(fileName)),

//         getSourceFile(fileName, languageVersion, onError) {
//             const file = fs.get(normalize(fileName));
//             if (file) {
//                 return ts.createSourceFile(
//                     normalize(fileName),
//                     file.content,
//                     languageVersion,
//                     true
//                 );
//             }
//             return defaultHost.getSourceFile(
//                 normalize(fileName),
//                 languageVersion,
//                 onError
//             );
//         },

//         directoryExists: (dirName) =>
//             fs.directoryExists(dirName) || defaultHost.directoryExists?.(dirName) || false,

//         getDirectories: (path) =>
//             [...fs.getDirectories(path), ...defaultHost.getDirectories?.(path) ?? []],

//         realpath: (path) =>
//             defaultHost.realpath?.(path) ?? path,

//         getCurrentDirectory: () =>
//             defaultHost.getCurrentDirectory(),

//         writeFile(fileName, content) {
//             fs.set(fileName, content);
//         },
//     };
// }

export const normalize = (p: string) => ts.sys.resolvePath(p);
