import ts, { factory } from "typescript";
import { Effect } from "effect"
import { createLayerDependency, type Dependency, type ImportClause, lowercaseFirstLetter, NodeCreator, uppercaseFirstLetter } from "./node.ts";
import { VFS } from "../lsp/vfs.ts";
import { Action } from "./action.ts";
import { Sequence } from "./sequence.ts";
import { ReconLanguageServer } from "src/lsp/lsp.ts";
import { ReconEnvBuilder } from "src/lsp/env.ts";

export class Selector extends NodeCreator {
    public dependencyNames: string[];
    constructor(name: string, basepath?: string) {
        super(name, basepath);
        this.args = factory.createArrayLiteralExpression();
        this.dependencyNames = [];
    }

    addArgs(args: ts.ArrayLiteralExpression) {
        this.args = args;
    }

    override addChild(child: Action | Sequence | Selector): void {
        super.addChild(child);
    }

    override addLayer(): void {
        this.layer = createSelectorLayer(this.name, this.layerBody, this.dependencies);
    }

    override addLayerBody(): void {
        this.layerBody = createSelectorLayerBody(this.dependencies);
    }

    override addLayerDependency(dependencyName: string): void {
        super.addLayerDependency(dependencyName);
        this.dependencyNames.push(dependencyName);
    }
}

export class SelectorBuilder extends Effect.Service<SelectorBuilder>()(
    "SelectorBuilder",
    {
        effect: Effect.gen(function* () {
            const vfs = yield* VFS;
            const languageServer = yield* ReconLanguageServer;
            const reconEnv = yield* ReconEnvBuilder;

            const currentSelector: Selector[] = [];
            const selectors: Map<string, Selector> = new Map();
            let count = 0;

            const buildSelector = () => {
                addSelector("selector_" + count, "./dist/selectors/");
                count += 1;
                const importClause: ImportClause = {
                    phaseModifier: false,
                    namedBindings: [
                        { name: "Data", isType: false },
                        { name: "Effect", isType: false },
                    ]
                }
                addImport("effect", importClause);
                selector().addError();
                addLayer();

                vfs.set(selector().path(), selector().print());
                languageServer.getSyntacticDiagnostics(selector().path());
            };
            const addChild = (selector: Selector, child: Action | Sequence | Selector) => {
                if (selector.dependencyNames.includes(uppercaseFirstLetter(child.name))) {
                    console.log(`${child.name} is already included as a dependency`);
                    return
                }
                selector.addChild(child);
                const parameters = child.declarationParameters;
                parameters.map(param => {
                    const paramType = param.type;
                    if (paramType && ts.isTypeReferenceNode(paramType)) {
                        const name = paramType.getText();
                        const localImport = reconEnv.getImport(name);
                        selector.addImport(localImport.moduleSpecifier, localImport.importClause)
                    }
                })

                vfs.set(selector.path(), selector.print());
                languageServer.getSyntacticDiagnostics(selector.path());
            }

            const addImport = (moduleSpecifier: string, importClause: ImportClause) => {
                selector().addImport(moduleSpecifier, importClause);
            };
            const addLayer = () => {
                selector().addLayer();
            };
            const addSelector = (name: string, basePath: string) => {
                const selector = new Selector(name, basePath);
                currentSelector.push(selector);
                selectors.set(name, selector);
            };
            const pop = () => currentSelector.pop();
            const selector = () => {
                const sel = currentSelector.at(-1);
                if (sel) {
                    return sel;
                }
                throw new Error("Selector Map Empty");
            };
            return { addChild, buildSelector, pop, selector } as const;
        })
    }
) { }

const createSelectorLayer = (layerName: string, body: ts.Statement[], dependencies: Dependency[]) => {
    const serviceElements: ts.Expression[] = [];
    const services = factory.createArrayLiteralExpression(serviceElements);
    const dependencyNames = dependencies.map(dep => dep.name);
    const layerDependencies = dependencyNames.map(dep => createLayerDependency(dep))

    dependencyNames.forEach(depName => {
        serviceElements.push(
            factory.createPropertyAccessExpression(
                factory.createIdentifier(depName),
                factory.createIdentifier("Default")
            )
        )
    })

    const layer = [
        factory.createClassDeclaration(
            [factory.createToken(ts.SyntaxKind.ExportKeyword)],
            factory.createIdentifier(layerName),
            undefined,
            [factory.createHeritageClause(
                ts.SyntaxKind.ExtendsKeyword,
                [factory.createExpressionWithTypeArguments(
                    factory.createCallExpression(
                        factory.createCallExpression(
                            factory.createPropertyAccessExpression(
                                factory.createIdentifier("Effect"),
                                factory.createIdentifier("Service")
                            ),
                            [factory.createTypeReferenceNode(
                                factory.createIdentifier(layerName),
                                undefined
                            )],
                            []
                        ),
                        undefined,
                        [
                            factory.createStringLiteral(layerName),
                            factory.createObjectLiteralExpression(
                                [
                                    factory.createPropertyAssignment(
                                        factory.createIdentifier("effect"),
                                        factory.createCallExpression(
                                            factory.createPropertyAccessExpression(
                                                factory.createIdentifier("Effect"),
                                                factory.createIdentifier("gen")
                                            ),
                                            undefined,
                                            [factory.createFunctionExpression(
                                                undefined,
                                                factory.createToken(ts.SyntaxKind.AsteriskToken),
                                                undefined,
                                                undefined,
                                                [],
                                                undefined,
                                                factory.createBlock(
                                                    [...layerDependencies, ...body],
                                                    true
                                                )
                                            )]
                                        )
                                    ),
                                    factory.createPropertyAssignment(
                                        factory.createIdentifier("dependencies"),
                                        services,
                                    )
                                ],
                                true
                            )
                        ]
                    ),
                    undefined
                )]
            )],
            []
        ),
    ];
    return layer;
}

const createSelectorLayerBody = (dependencies: Dependency[]) => {
    if (dependencies.length === 0) {
        throw new Error("Dependencies Array Cannot be Zero");
    }
    const effects: ts.Expression[] = [];
    const callParameters = dependencies[0]!.callParameters;
    const declarationParameters = dependencies[0]!.declarationParameters;

    for (const dependency of dependencies) {
        const effect = factory.createCallExpression(
            factory.createPropertyAccessExpression(
                factory.createIdentifier(lowercaseFirstLetter(dependency.name)),
                factory.createIdentifier("update")
            ),
            undefined,
            callParameters
        )
        effects.push(effect)
    }

    const updateBody = [
        factory.createVariableStatement(
            undefined,
            factory.createVariableDeclarationList(
                [factory.createVariableDeclaration(
                    factory.createIdentifier("effects"),
                    undefined,
                    undefined,
                    factory.createArrayLiteralExpression(
                        effects,
                        false
                    )
                )],
                ts.NodeFlags.Const
            )
        ),
        factory.createReturnStatement(factory.createBinaryExpression(
            factory.createIdentifier("yield"),
            factory.createToken(ts.SyntaxKind.AsteriskToken),
            factory.createCallExpression(
                factory.createPropertyAccessExpression(
                    factory.createIdentifier("Effect"),
                    factory.createIdentifier("firstSuccessOf")
                ),
                undefined,
                [factory.createIdentifier("effects")]
            )
        ))
    ];

    const selectorBody = [
        factory.createVariableStatement(
            undefined,
            factory.createVariableDeclarationList(
                [factory.createVariableDeclaration(
                    factory.createIdentifier("update"),
                    undefined,
                    undefined,
                    factory.createArrowFunction(
                        undefined,
                        undefined,
                        declarationParameters,
                        undefined,
                        factory.createToken(ts.SyntaxKind.EqualsGreaterThanToken),
                        factory.createCallExpression(
                            factory.createPropertyAccessExpression(
                                factory.createIdentifier("Effect"),
                                factory.createIdentifier("gen")
                            ),
                            undefined,
                            [factory.createFunctionExpression(
                                undefined,
                                factory.createToken(ts.SyntaxKind.AsteriskToken),
                                undefined,
                                undefined,
                                [],
                                undefined,
                                factory.createBlock(
                                    [...updateBody],
                                    true
                                )
                            )]
                        )
                    )
                )],
                ts.NodeFlags.Const
            )
        ),
        factory.createReturnStatement(factory.createAsExpression(
            factory.createObjectLiteralExpression(
                [factory.createShorthandPropertyAssignment(
                    factory.createIdentifier("update"),
                    undefined
                )],
                false
            ),
            factory.createTypeReferenceNode(
                factory.createIdentifier("const"),
                undefined
            )
        ))
    ];
    return selectorBody;
}
