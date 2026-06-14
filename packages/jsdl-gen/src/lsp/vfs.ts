import ts from "typescript";
import fs from "fs";
import path from "path";
import { Effect } from "effect";

type VirtualFile = {
    version: number;
    content: string;
};

export class VFS extends Effect.Service<VFS>()(
    "VirtualFS",
    {
        effect: Effect.sync(() => {
            const files = new Map<string, VirtualFile>();
            const proto = {
                set(fileName: string, content: string) {
                    const prev = files.get(normalize(fileName));
                    const newFile = {
                        version: (prev?.version ?? 0) + 1,
                        content,
                    }
                    files.set(normalize(fileName), newFile);
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

            // proto.set(normalize('dist/types.ts'),
            //     `export enum Status {
            //     READY = "ready",
            //     RUNNING = "running",
            //     SUCCESS = "success",
            //     FAILED = "failed"
            // }
            // `)
            return proto;
        })
    }
) { }

export const normalize = (p: string) => ts.sys.resolvePath(p);
