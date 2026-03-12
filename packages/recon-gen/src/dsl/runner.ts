import ts, { factory } from "typescript";
import { Effect } from "effect";
import { ReconLanguageServer } from "src/lsp/lsp.ts";
import { VFS } from "src/lsp/vfs.ts";
import { createRelativeImportPath, NodeCreator, type Dependency, type ImportClause, type ImportSpecifier } from "./node.ts";
import type { Root } from "./root.ts";

export class Runner extends NodeCreator {
    public dependencyNames: string[];

    constructor(name: string, basepath?: string) {
        super(name, basepath);
        this.dependencyNames = [];
    }

    override addLayer(): void {
        this.layer = createRunnerLayer(this.name, this.layerBody, this.dependencyNames);
    }
    override addLayerBody(): void {
        this.layerBody = createRunnerLayerBody(this.dependencyNames);
    }

    override addLayerDependency(dependencyName: string): void {
        const dependency = createLayerDependency(dependencyName);
        // this.layerDependencies.push(dependency);
        this.dependencyNames.push(dependencyName);
    }
}
export class ReconRunner extends Effect.Service<ReconRunner>()(
    "ReconRunner",
    {
        effect: Effect.gen(function* () {
            const vfs = yield* VFS;
            const languageServer = yield* ReconLanguageServer;
            const runner = new Runner("runner", "./recon/");

            const buildRunner = () => {
                const effectImportClause: ImportClause = {
                    phaseModifier: false,
                    namedBindings: [
                        { name: "Effect", isType: false }
                    ]
                }
                const platformImportClause: ImportClause = {
                    phaseModifier: false,
                    namedBindings: [
                        { name: "NodeContext", isType: false },
                        { name: "NodeRuntime", isType: false }
                    ]
                }
                runner.addImport("effect", effectImportClause);
                runner.addImport("@effect/platform-node", platformImportClause);

                vfs.set(runner.path(), runner.print());
                languageServer.getSyntacticDiagnostics(runner.path());
            };

            const addChild = (child: Root) => {
                if (runner.dependencyNames.includes(child.name)) {
                    return;
                }
                const relativePath = createRelativeImportPath(runner.path(), child.path());
                const importClause: ImportClause = {
                    namedImport: undefined,
                    namedBindings: [{ propertyName: undefined, name: child.name, isType: false }]
                };
                runner.addImport(relativePath, importClause);
                runner.addLayerDependency(child.name);
                runner.addLayerBody();

                vfs.set(runner.path(), runner.print());
                languageServer.getSyntacticDiagnostics(runner.path());
            }
            
            return { addChild, buildRunner } as const;
        })
    }
) { }

const createLayerDependency = (dependencyName: string) => {
    const layerName = dependencyName + "Program";
    const dep = factory.createVariableStatement(
        undefined,
        factory.createVariableDeclarationList(
            [factory.createVariableDeclaration(
                factory.createIdentifier(layerName),
                undefined,
                undefined,
                factory.createYieldExpression(
                    factory.createToken(ts.SyntaxKind.AsteriskToken),
                    factory.createIdentifier(dependencyName)
                )
            )],
            ts.NodeFlags.Const
        )
    )
    return dep;
}

const createRunnerLayer = (layerName: string, body: ts.Statement[], dependencyNames: string[]) => {
    const serviceElements: ts.Expression[] = [];
    const services = factory.createArrayLiteralExpression(serviceElements);
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
                                [factory.createPropertyAssignment(
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
                                    factory.createIdentifier("accessors"),
                                    factory.createTrue()
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
        factory.createVariableStatement(
            undefined,
            factory.createVariableDeclarationList(
                [factory.createVariableDeclaration(
                    factory.createIdentifier("program"),
                    undefined,
                    undefined,
                    factory.createCallExpression(
                        factory.createPropertyAccessExpression(
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
                                        [factory.createExpressionStatement(factory.createYieldExpression(
                                            factory.createToken(ts.SyntaxKind.AsteriskToken),
                                            factory.createCallExpression(
                                                factory.createPropertyAccessExpression(
                                                    factory.createIdentifier("runner"),
                                                    factory.createIdentifier("run")
                                                ),
                                                undefined,
                                                []
                                            )
                                        ))],
                                        true
                                    )
                                )]
                            ),
                            factory.createIdentifier("pipe")
                        ),
                        undefined,
                        [factory.createCallExpression(
                            factory.createPropertyAccessExpression(
                                factory.createIdentifier("Effect"),
                                factory.createIdentifier("provide")
                            ),
                            undefined,
                            [factory.createPropertyAccessExpression(
                                factory.createIdentifier("runner"),
                                factory.createIdentifier("Default")
                            )]
                        )]
                    )
                )],
                ts.NodeFlags.Const
            )
        ),
        factory.createExpressionStatement(factory.createCallExpression(
            factory.createPropertyAccessExpression(
                factory.createIdentifier("NodeRuntime"),
                factory.createIdentifier("runMain")
            ),
            undefined,
            [factory.createCallExpression(
                factory.createPropertyAccessExpression(
                    factory.createIdentifier("program"),
                    factory.createIdentifier("pipe")
                ),
                undefined,
                [factory.createCallExpression(
                    factory.createPropertyAccessExpression(
                        factory.createIdentifier("Effect"),
                        factory.createIdentifier("provide")
                    ),
                    undefined,
                    [factory.createPropertyAccessExpression(
                        factory.createIdentifier("NodeContext"),
                        factory.createIdentifier("layer")
                    )]
                )]
            )]
        ))
    ];
    return layer;
}

const createRunnerLayerBody = (dependencyNames: string[]) => {
    const layerBody = [
        factory.createVariableStatement(
            undefined,
            factory.createVariableDeclarationList(
                [factory.createVariableDeclaration(
                    factory.createIdentifier("run"),
                    undefined,
                    undefined,
                    factory.createArrowFunction(
                        undefined,
                        undefined,
                        [],
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
                                    [],
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
                    factory.createIdentifier("run"),
                    undefined
                )],
                false
            ),
            factory.createTypeReferenceNode(
                factory.createIdentifier("const"),
                undefined
            )
        ))
    ]
    return layerBody;
}