import { Effect } from "effect";
import ts, { Node } from "typescript";
import { ReconLanguageServer } from "./lsp.ts";
import { getEscapedText } from "./node.ts";

export class ReconEnvBuilder extends Effect.Service<ReconEnvBuilder>()(
    "ReconEnvBuilder",
    {
        effect: Effect.gen(function* () {
            const languageServer = yield* ReconLanguageServer;
            const importNodes = new Map<string, { namedImport: string | undefined, namedBindings: string[] }>();
            const packageMap = new Map<string, string>();

            const collectIdentifiers = (node: Node, out: ts.Identifier[]) => {
                if (ts.isIdentifier(node)) {
                    out.push(node);
                }
                ts.forEachChild(node, child => collectIdentifiers(child, out))
            }

            const checkSymbols = (runFunction: ts.ArrowFunction) => {
                const identifiers: ts.Identifier[] = [];
                collectIdentifiers(runFunction, identifiers);
                const exportNodes = new Map<string, { namedImport: string | undefined, namedBindings: string[] }>();

                const program = languageServer.getProgram();
                const checker = program?.getTypeChecker();
                identifiers.forEach(identifier => {
                    const symbol = checker?.getSymbolAtLocation(identifier);
                    if (!symbol) {
                        return
                    }
                    if (symbol.flags & ts.SymbolFlags.Alias) {
                        const packageName = packageMap.get(getEscapedText(identifier));
                        if (!packageName) {
                            return
                        }
                        const exportNode = importNodes.get(packageName)
                        if (exportNode) {
                            exportNodes.set(packageName, exportNode);
                        }
                    }
                })
                return exportNodes;
            }

            const addImport = (declaration: ts.ImportDeclaration) => {
                const importClause = declaration.importClause;
                if (!importClause) {
                    //malformed import declaeation
                    return
                }
                const packageName = declaration.moduleSpecifier;
                const namedImport = importClause.name;
                const namedBindings = importClause.namedBindings;
                const bindings: string[] = [];
                namedBindings?.forEachChild(child => {
                    packageMap.set(getEscapedText(child), getEscapedText(packageName));
                    bindings.push(child.getText());
                })
                const statement = {
                    namedImport: namedImport?.text,
                    namedBindings: bindings
                }
                importNodes.set(getEscapedText(packageName), statement)
            }

            const init = (envNodes: Node[]) => {
                for (const envNode of envNodes) {
                    if (ts.isImportDeclaration(envNode)) {
                        addImport(envNode);
                    }
                }
            }

            return { init, checkSymbols } as const
        })
    }
) { }