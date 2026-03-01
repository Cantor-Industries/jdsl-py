import ts, { type Node, type SourceFile } from "typescript";
// import type { Node, SourceFile, factory } from "typescript";
import { Effect } from "effect";
import { getEscapedText, type ImportSpecifier } from "../dsl/node.ts";
import { ReconEnvBuilder } from "./env.ts";
import { ReconLanguageServer } from "./lsp.ts";

export class ImportResolver extends Effect.Service<ImportResolver>()(
    "ImportResolver",
    {
        effect: Effect.gen(function* () {
            const reconEnv = yield* ReconEnvBuilder;
            const languageServer = yield* ReconLanguageServer;

            const extractDeclarations = (node: ts.ImportDeclaration, checker: ts.TypeChecker) => {
                let importedSymbol: Node | undefined;

                const importClause = node.importClause;
                if (!importClause) {
                    throw new Error(`Failed to resolve import clause at ${node.getText()}`);
                }
                if (importClause.name) {
                    importedSymbol = importClause.name
                } else {
                    importClause.namedBindings?.forEachChild(child => {
                        if (ts.isImportSpecifier(child)) {
                            importedSymbol = child.name
                        }
                    })
                }
                if (!importedSymbol) {
                    throw new Error(`Failed to resolve import clause at ${node.getText()}`);
                }
                const symbol = checker.getSymbolAtLocation(importedSymbol);
                if (!symbol) {
                    throw new Error(`Failed to resolve symbol ${importedSymbol.getText()}`);
                }
                const visitedSymbols = new Set<ts.Symbol>();
                let symbolAlias = symbol;
                while (symbolAlias.flags & ts.SymbolFlags.Alias) {
                    if (visitedSymbols.has(symbolAlias)) {
                        break;
                    }
                    visitedSymbols.add(symbolAlias);
                    const aliased = checker?.getAliasedSymbol(symbolAlias);
                    if (!aliased) {
                        break;
                    }
                    symbolAlias = aliased;
                }
                const declarations = symbolAlias.getDeclarations();

                if (!declarations || declarations.length === 0) {
                    throw new Error(`Failed to resolve symbol alias declarations for ${checker.symbolToString(symbolAlias)}`);
                }
                return declarations
            }

            const resolveModuleSpecifier = (node: ts.ImportDeclaration, checker: ts.TypeChecker) => {
                const declarations = extractDeclarations(node, checker);
                const declaration = declarations[0];
                const declPath = declaration?.getSourceFile().fileName ?? node.moduleSpecifier.getText();
                return declPath;
            }
            const resolveSymbol = (node: ts.ImportDeclaration, checker: ts.TypeChecker) => {
                const declarations = extractDeclarations(node, checker);
                const declaration = declarations[0];
                const sourceFile = declaration?.getSourceFile();
                const importNodes: ts.ImportDeclaration[] = [];

                if (!sourceFile) {
                    throw new Error(`Failed to resolve sourcefile for ${node.getText()}`);
                }
                const symbolVisitor = (node: Node): Node => {
                    if (ts.isImportDeclaration(node)) {
                        importNodes.push(node);
                    }
                    return node.forEachChild(symbolVisitor)!
                }
                ts.visitNode(sourceFile, symbolVisitor, undefined);
                return importNodes;

            }

            const resolveImport = (node: ts.ImportDeclaration) => {
                const program = languageServer.getProgram();
                const checker = program?.getTypeChecker();

                if (!checker) {
                    throw new Error("LanguageServer Failed on Checker");
                }
                const packageName = getEscapedText(node.moduleSpecifier);
                let moduleSpecifier: string;

                if (packageName.startsWith("./") || packageName.startsWith("../") || packageName.startsWith("/")) {
                    const importNodes = resolveSymbol(node, checker);
                    importNodes.forEach(node => {
                        resolveImport(node);
                    })
                    moduleSpecifier = resolveModuleSpecifier(node, checker);
                } else {
                    moduleSpecifier = packageName;
                }

                const importClause = node.importClause;
                const namedImport = importClause?.name;
                const namedBindings = importClause?.namedBindings;
                const bindings: ImportSpecifier[] = [];

                namedBindings?.forEachChild(child => {
                    if (namedBindings && ts.isImportSpecifier(child)) {
                        const propertyName = child.propertyName;
                        const name = child.name
                        console.log(propertyName?.text, "->", name.text)
                        bindings.push({propertyName: propertyName?.text, name: name.text, isType: child.isTypeOnly})
                    }
                })
                const importDeclarationObj = {
                    [moduleSpecifier]: {
                        namedImport: namedImport?.text,
                        namedBindings: bindings,
                        node: node,
                        phaseModifier: importClause?.phaseModifier ? true : false
                    }
                }
                reconEnv.addImport(importDeclarationObj);
            }
            return { resolveImport } as const;
        })
    }
) { }

export class ReconResolver extends Effect.Service<ReconResolver>()(
    "ReconResolver",
    {
        effect: Effect.gen(function* () {
            const importResolver = yield* ImportResolver;
            const toolsNodes: Node[] = [];
            const skillsNodes: Node[] = [];

            const visitor = (node: Node): Node => {
                if (ts.isSatisfiesExpression(node)) {
                    const satisfiesType = node.getChildAt(2);
                    if (satisfiesType.getText().startsWith("Tool")) {
                        toolsNodes.push(node.getChildAt(0));
                    } else if (satisfiesType.getText().startsWith("Skill")) {
                        skillsNodes.push(node.getChildAt(0));
                    }
                }

                if (ts.isImportDeclaration(node)) {
                    console.log("Processing:", node.getText());
                    importResolver.resolveImport(node);
                }

                return node.forEachChild(visitor)!
            }

            const resolve = (sourceFile: SourceFile) => {
                ts.visitNode(sourceFile, visitor, undefined);
                return { toolsNodes, skillsNodes }
            }

            return { resolve } as const;
        }),
        dependencies: [ImportResolver.Default]
    }
) { }