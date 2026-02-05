import ts, { LanguageServiceHost } from "typescript";
import { normalize, VFS } from "./vfs.ts"
import { Effect } from "effect";

export class ReconCompilerOptions extends Effect.Service<ReconCompilerOptions>()(
	"ReconCompilerOptions",
	{
		effect: Effect.sync(() => {
			console.log("RECON COMPILEROPTIONS INIT");
			const options: ts.CompilerOptions = {
				target: ts.ScriptTarget.ESNext,
				module: ts.ModuleKind.NodeNext,
				moduleResolution: ts.ModuleResolutionKind.NodeNext,
				strict: true,
				sourceMap: true,
				esModuleInterop: true,
				skipLibCheck: false,
			};
			return options
		})
	}
) { }

export class ReconLanguageServiceHost extends Effect.Service<ReconLanguageServiceHost>()(
	"ReconLanguageServer",
	{
		effect: Effect.gen(function* () {
			console.log("RECON LANGUAGE SERVICE HOST INIT");
			const files = yield* VFS;
			const options = yield* ReconCompilerOptions;

			const serviceHost: LanguageServiceHost = {
				getScriptFileNames: () => {
					const libFile = ts.getDefaultLibFilePath(options);
					return [...files.fileNames(), libFile];
				},

				getScriptVersion: (fileName: string) => {
					const file = files.get(fileName);
					return file ? file.version.toString() : "0";
				},
				getScriptSnapshot: (fileName) => {
					const file = files.get(fileName);
					if (file) {
						return ts.ScriptSnapshot.fromString(file.content);
					}
					const text = ts.sys.readFile(fileName);
					return text ? ts.ScriptSnapshot.fromString(text) : undefined;
				},
				getCompilationSettings: () => {
					return options
				},
				getCurrentDirectory: () => {
					return ts.sys.getCurrentDirectory();
				},
				getDefaultLibFileName: (options: ts.CompilerOptions) => {
					return ts.getDefaultLibFilePath(options);
				},
				fileExists: (fileName) => {
					return files.has(normalize(fileName)) || ts.sys.fileExists(fileName);
				},
				readFile: (fileName) => {
					return files.get(normalize(fileName))?.content ?? ts.sys.readFile(fileName);
				},
				directoryExists: (dirName) => {
					return files.directoryExists(dirName) || ts.sys.directoryExists?.(dirName) || false;
				},
				getDirectories: (path) => {
					return [...files.getDirectories(path), ...ts.sys.getDirectories?.(path) ?? []];
				}
			};
			return serviceHost
		}),
		dependencies: [ReconCompilerOptions.Default]
	}
) { }

export class ReconLanguageServer extends Effect.Service<ReconLanguageServer>()(
	"ReconLanguageServer",
	{
		effect: Effect.gen(function* () {
			console.log("RECON LANGUAGE SERVER INIT");
			const host = yield* ReconLanguageServiceHost;
			const service = ts.createLanguageService(host);
			return service;
		}),
		dependencies: [ReconLanguageServiceHost.Default]
	}
) { }
