import ts, { type Node, type SourceFile } from "typescript";
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

            const extractSymbolAlias = (node: Node, checker: ts.TypeChecker) => {
                const symbol = checker.getSymbolAtLocation(node);
                if (!symbol) {
                    throw new Error(`Failed to resolve symbol ${node.getText()}`);
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
                return symbolAlias;
            }

            const extractImportDeclarations = (node: ts.ImportDeclaration, checker: ts.TypeChecker) => {
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
                    throw new Error(`Failed to resolve import clause ${importClause.getText()}`);
                }
                const symbolAlias = extractSymbolAlias(importedSymbol, checker);
                const declarations = symbolAlias.getDeclarations();

                if (!declarations || declarations.length === 0) {
                    throw new Error(`Failed to resolve symbol alias declarations for ${checker.symbolToString(symbolAlias)}`);
                }
                return declarations
            }

            const resolveModuleSpecifier = (node: ts.ImportDeclaration, checker: ts.TypeChecker) => {
                const moduleSpecifier = getEscapedText(node.moduleSpecifier);
                if (moduleSpecifier.startsWith("./") || moduleSpecifier.startsWith("../")) {
                    const declarations = extractImportDeclarations(node, checker);
                    const declaration = declarations[0];
                    const declPath = declaration?.getSourceFile().fileName ?? node.moduleSpecifier.getText();
                    return declPath;
                }
                return moduleSpecifier;
            }
            const resolveImportedSymbols = (node: ts.ImportDeclaration, checker: ts.TypeChecker) => {
                const declarations = extractImportDeclarations(node, checker);
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

                const extractImportFromDeclaration = (node: ts.ImportDeclaration, moduleSpecifier: string) => {
                    const importClause = node.importClause;
                    const namedImport = importClause?.name;
                    const namedBindings = importClause?.namedBindings;
                    const bindings: ImportSpecifier[] = [];

                    if (!namedBindings) {
                        return;
                    }

                    if (ts.isNamespaceImport(namedBindings)) {
                        bindings.push({ propertyName: "*", name: namedBindings.name.text, isType: false })
                    }

                    if (ts.isNamedImportBindings(namedBindings)) {
                        namedBindings.forEachChild(child => {
                            if (ts.isImportSpecifier(child)) {
                                const propertyName = child.propertyName;
                                const name = child.name
                                bindings.push({ propertyName: propertyName?.text, name: name.text, isType: child.isTypeOnly })
                            }
                        })
                    }

                    const importDeclarationObj = {
                        [moduleSpecifier]: {
                            namedImport: namedImport?.text,
                            namedBindings: bindings,
                            node: node,
                            phaseModifier: importClause?.phaseModifier ? true : false
                        }
                    }
                    return importDeclarationObj;
                }

                if (!checker) {
                    throw new Error("LanguageServer Failed on Checker");
                }
                const packageName = getEscapedText(node.moduleSpecifier);
                let moduleSpecifier: string;
                let importNodes: ts.ImportDeclaration[] = [];

                if (packageName.startsWith("./") || packageName.startsWith("../")) {
                    importNodes = resolveImportedSymbols(node, checker);
                    moduleSpecifier = resolveModuleSpecifier(node, checker);
                } else {
                    moduleSpecifier = packageName;
                }

                const importDeclarationObj = extractImportFromDeclaration(node, moduleSpecifier);
                if (!importDeclarationObj) {
                    return;
                }
                reconEnv.addImport(importDeclarationObj);

                importNodes.forEach(importedNode => {
                    const importedModuleSpecifier = resolveModuleSpecifier(importedNode, checker)
                    const declarationObj = extractImportFromDeclaration(importedNode, importedModuleSpecifier);
                    if (declarationObj) {
                        reconEnv.addImport(declarationObj);
                    }
                });
            }
            return { extractSymbolAlias, resolveImport } as const;
        })
    }
) { }

export class GlobalResolver extends Effect.Service<GlobalResolver>()(
    "GlobalResolver",
    {
        effect: Effect.gen(function* () {
            const glbl = "";

            return { glbl } as const;
        })
    }
){}

export class ReconResolver extends Effect.Service<ReconResolver>()(
    "ReconResolver",
    {
        effect: Effect.gen(function* () {
            const importResolver = yield* ImportResolver;
            const toolsNodes: Node[] = [];
            const skillsNodes: Node[] = [];

            const visitor = (node: Node): Node => {
                if (ts.isSatisfiesExpression(node)) {
                    const satisfiesType = node.type;
                    if (satisfiesType.getText().startsWith("Tool")) {
                        const tool = node.expression;
                        toolsNodes.push(tool);
                    } else if (satisfiesType.getText().startsWith("Skill")) {
                        const skill = node.expression
                        skillsNodes.push(skill);
                    }
                }

                if (ts.isImportDeclaration(node)) {
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