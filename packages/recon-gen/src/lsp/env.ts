import path from "path";
import ts, { factory, type Node, type VariableDeclaration } from "typescript";
import { Effect } from "effect";

import { ReconLanguageServer } from "./lsp.ts";
import { getEscapedText } from "../dsl/node.ts";
import type { ImportClause, ImportDeclaration } from "../dsl/node.ts";

export class ReconEnvBuilder extends Effect.Service<ReconEnvBuilder>()(
    "ReconEnvBuilder",
    {
        effect: Effect.gen(function* () {
            const languageServer = yield* ReconLanguageServer;
            const importNodes = new Map<string, ImportClause>();
            const packageMap = new Map<string, string>();

            const collectIdentifiers = (node: Node, out: ts.Identifier[]) => {
                if (ts.isIdentifier(node)) {
                    out.push(node);
                }
                ts.forEachChild(node, child => collectIdentifiers(child, out))
            }
            const checkImport = (name: string) => {
                const namedBinding = packageMap.get(name);
                if (!namedBinding) {
                    console.log("Could not resolve", name)
                    return false;
                }
                const packageName = importNodes.get(namedBinding);
                if (!packageName) {
                    return false;
                }
                return true;
            }

            const getImport = (name: string) => {
                const moduleSpecifier = packageMap.get(name);
                if (!moduleSpecifier) {
                    throw new Error(`Could not resolve ${name}`)
                }
                const importClause = importNodes.get(moduleSpecifier);
                if (!importClause) {
                    throw new Error(`Could not resolve package for ${name}`)
                }
                return { moduleSpecifier, importClause } as const
            }

            const getImportNode = (name: string) => {
                if (!checkImport(name)) {
                    throw new Error(`${name} import not found/invalid`)
                }
                const namedBinding = packageMap.get(name);
                if (!namedBinding) {
                    throw new Error(`invalid ${name} import`);
                }
                const node = importNodes.get(namedBinding)?.node;
                if (!node) {
                    throw new Error(`Could not resolve node for ${name}`);
                }

                const importClause = node.importClause;
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
                    if (ts.isImportSpecifier(child)) {
                        console.log(`Comparing ${name} against ${child.name.text}`);
                        if (name === child.name.text) binding = child.name
                    }
                })
                if (!binding) {
                    throw new Error(`missing import clause for ${name}`);
                }
                return binding;
            }

            const hasAsyncModifier = (fn: ts.ArrowFunction | ts.FunctionDeclaration | ts.FunctionExpression) => {
                return !!fn.modifiers?.some(m => m.kind === ts.SyntaxKind.AsyncKeyword);
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
                const signature = signatures[0]!;
                // const parameters = signature.getParameters();
                let parameters: ts.ParameterDeclaration[];
                // const declaration = signature.getDeclaration();
                let declaration: ts. FunctionDeclaration | ts.FunctionExpression | ts.ArrowFunction | undefined;
                const valueDeclaration = symbolAlias?.valueDeclaration as ts.FunctionDeclaration | ts.VariableDeclaration;
                // console.log("Value declaration kind:", valueDeclaration.kind)
                if (ts.isFunctionDeclaration(valueDeclaration!)) {
                    if (hasAsyncModifier(valueDeclaration)) console.log(callName, "is an async function declaration");
                    else console.log(callName, "is a function declaration");
                    declaration = valueDeclaration;
                } else if (ts.isVariableDeclaration(valueDeclaration)) {
                    console.log(callName, "is a variable statement");
                    // const declarationList = valueDeclaration.;
                    // const variableDeclaration = declarationList.declarations[0];
                    const initializer = valueDeclaration.initializer;
                    // console.log("----->", initializer?.getFullText())
                    // console.log("----->", initializer?.kind);
                    if (initializer && (ts.isFunctionExpression(initializer) || ts.isArrowFunction(initializer))) {
                        declaration = initializer;
                    }
                } 
                // else {
                //     throw new Error(`Resolved declaration for ${callName} is neither a FunctionDeclaration, FunctionExpression, or ArrowFunction`);
                // }
                if (!declaration) {
                    throw new Error(`Resolved declaration for ${callName} is neither a FunctionDeclaration, FunctionExpression, or ArrowFunction`);
                }
                // console.log(valueDeclaration?.getFullText());
                parameters = [...declaration.parameters]
                const returnType = checker?.getReturnTypeOfSignature(signature);

                // const parameters = valueDeclaration.parameters
                const forwardedArgs = parameters.map(param => {
                    // check for spread operator
                    // if (param.dotDotDotToken) {
                    //     return factory.createSpreadElement(factory.createIdentifier(param.name.getText()))
                    // }
                    return factory.createIdentifier(param.name.getText())
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
                    hasAsyncModifier(declaration) ? [factory.createModifier(ts.SyntaxKind.AsyncKeyword)] : undefined, // isAsync?
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
                const exportNodes = new Map<string, ImportClause>();

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

            const addImport = (declaration: ImportDeclaration) => {

                const moduleSpecifier = Object.keys(declaration)[0]!;
                const importDeclarationObj = declaration[moduleSpecifier];
                const namedImport = importDeclarationObj?.namedImport
                if (namedImport) {
                    packageMap.set(namedImport, moduleSpecifier);
                }
                const namedBindings = importDeclarationObj?.namedBindings;
                namedBindings?.forEach(child => {
                    packageMap.set(child.name, moduleSpecifier);
                })
                importNodes.set(moduleSpecifier, importDeclarationObj!);

            }

            return { addImport, checkImport, checkSymbols, getImport, getRunFunction } as const
        })
        
    }
) { }