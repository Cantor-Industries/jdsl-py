import { Effect } from "effect";
import ts, { factory, type Node } from "typescript";
import path from "path";
import { ReconLanguageServer } from "./lsp.ts";
import { getEscapedText } from "../dsl/node.ts";

export class ReconEnvBuilder extends Effect.Service<ReconEnvBuilder>()(
    "ReconEnvBuilder",
    {
        effect: Effect.gen(function* () {
            const languageServer = yield* ReconLanguageServer;
            const importNodes = new Map<string, { namedImport: string | undefined, namedBindings: string[], node: ts.ImportDeclaration }>();
            const packageMap = new Map<string, string>();

            const collectIdentifiers = (node: Node, out: ts.Identifier[]) => {
                if (ts.isIdentifier(node)) {
                    out.push(node);
                }
                ts.forEachChild(node, child => collectIdentifiers(child, out))
            }
            const checkImport = (name: string) => {
                console.log("Checking import:", name)
                const namedBinding = packageMap.get(name);
                if (!namedBinding) {
                    console.log("Could not resolve", name)
                    return false;
                }
                const packageName = importNodes.get(namedBinding);
                if (!packageName) {
                    return false;
                }
                console.log("Import found:", name)
                return true;
            }

            const getImport = (name: string) => {
                const packageName = packageMap.get(name);
                if (!packageName) {
                    throw new Error(`Could not resolve ${name}`)
                }
                const namedBinding = importNodes.get(packageName);
                if (!packageName) {
                    throw new Error(`Could not resolve package for ${name}`)
                }
                console.log(packageName, "=>", namedBinding?.namedBindings, ",", namedBinding?.namedImport);
                return { namedBinding, packageName } as const
            }

            const getImportNode = (name: string) => {
                if (!checkImport(name)) {
                    throw new Error(`${name} import not found/invalid`)
                }
                const namedBinding = packageMap.get(name)!;
                const nodes = importNodes.get(namedBinding)!.node;

                const importClause = nodes.importClause;
                if (!importClause) {
                    throw new Error(`could not find import clause for ${name}`);
                }
                const namedImport = importClause.name;
                if (namedImport?.text === name) {
                    return namedImport;
                }
                const namedBindings = importClause.namedBindings;
                let binding: Node | undefined;
                namedBindings?.forEachChild(child => {
                    if (getEscapedText(child) === name) {
                        // get identifier behind import specifier
                        binding = child.getChildAt(0);
                        return
                    }
                })
                if (!binding) {
                    throw new Error(`missing import clause for ${name}`);
                }
                return binding;
            }
            const getPath = (node: Node) => {
                const program = languageServer.getProgram();
                const checker = program?.getTypeChecker();
                const symbol = checker?.getSymbolAtLocation(node);

                if (!symbol) {
                    throw new Error(`Unable to resolve symbol ${node.getText()}`);
                }
                const symbolAlias = checker?.getAliasedSymbol(symbol);
                const symbolSourcefile = symbolAlias?.valueDeclaration?.getSourceFile();

                if (!symbolSourcefile) {
                    throw new Error(`Unable to resolve symbol ${symbol.name}`);
                }

                console.log(node.getText(), "=>", symbolSourcefile.fileName);
                return symbolSourcefile.fileName;
            }

            const getRunFunction = (callName: string) => {
                const program = languageServer.getProgram();
                const checker = program?.getTypeChecker();
                const node = getImportNode(callName);
                const symbol = checker?.getSymbolAtLocation(node);
                if (!symbol) {
                    throw new Error(`Unable to resolve symbol ${node.getText()}`);
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
                    symbolAlias = aliased
                }
                const symbolType = checker?.getTypeOfSymbolAtLocation(symbolAlias!, symbolAlias?.valueDeclaration!);
                const signatures = symbolType?.getCallSignatures();
                if (!signatures || signatures?.length === 0) {
                    throw new Error(`${callName} not callable`);
                }
                console.log(`${callName} is a top-level import has: ${signatures.length} signatures`);
                const signature = signatures[0]!;
                const parameters = signature.getParameters();
                const declaration = signature.getDeclaration();
                const valueDeclaration = symbolAlias?.valueDeclaration;
                const returnType = checker?.getReturnTypeOfSignature(signature);

                const forwardedArgs = parameters.map(param => {
                    const name = param.name;
                    // check for spread operator
                    return factory.createIdentifier(name)
                })
                const typeParams = declaration.typeParameters;
                const callTypeArgs = typeParams && typeParams.length > 0 ?
                    typeParams?.map(tp => factory.createTypeReferenceNode(tp.name.text)) : undefined

                const callExpression = factory.createCallExpression(
                    factory.createIdentifier(callName),
                    callTypeArgs,
                    forwardedArgs
                )

                const runFunction = factory.createArrowFunction(
                    undefined, // isAsync?
                    declaration.typeParameters,
                    declaration.parameters,
                    declaration.type,
                    factory.createToken(ts.SyntaxKind.EqualsGreaterThanToken),
                    callExpression
                );
                return runFunction;
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
                    //malformed import declaration
                    return
                }
                const packageName = declaration.moduleSpecifier;
                const namedImport = importClause.name;
                if (namedImport) {
                    packageMap.set(getEscapedText(namedImport), getEscapedText(packageName))
                }
                const namedBindings = importClause.namedBindings;
                const bindings: string[] = [];
                namedBindings?.forEachChild(child => {
                    packageMap.set(getEscapedText(child), getEscapedText(packageName));
                    bindings.push(child.getText());
                })
                const statement = {
                    namedImport: namedImport?.text,
                    namedBindings: bindings,
                    node: declaration
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

            return { init, checkImport, checkSymbols, getImport, getRunFunction } as const
        })
    }
) { }