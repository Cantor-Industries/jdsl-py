import ts, { LanguageServiceHost } from "typescript";
import { normalize, VFS } from "./vfs.ts"
import { Effect } from "effect";

export class ReconCompilerOptions extends Effect.Service<ReconCompilerOptions>()(
	"ReconCompilerOptions",
	{
		effect: Effect.sync(() => {
			console.log("RECON COMPILEROPTIONS INIT");
			const options: ts.CompilerOptions = {
				target: ts.ScriptTarget.Latest,
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
					return files.fileNames();
				},
				getScriptVersion: (fileName: string) => {
					const file = files.get(fileName);
					return file ? file.version.toString() : "0";
				},
				getScriptSnapshot: (fileName: string) => {
					const file = files.get(fileName);
					if (!file) return undefined;
					return ts.ScriptSnapshot.fromString(file.content);
				},
				getCompilationSettings: () => {
					return options
				},
				getCurrentDirectory: () => {
					return normalize("./");
				},
				getDefaultLibFileName: (options: ts.CompilerOptions) => {
					return ts.getDefaultLibFilePath(options);
				},
				fileExists: (fileName) => {
					return files.has(normalize(fileName));
				},
				readFile: (fileName) => {
					return files.get(normalize(fileName))?.content;
				},
				directoryExists: (dirName) => {
					return files.directoryExists(dirName);
				},
				getDirectories: (path) => {
					return files.getDirectories(path);
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
