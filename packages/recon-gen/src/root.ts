import ts, { factory } from "typescript";
import { Effect } from "effect";
import { createLayer, createRelativeImportPath, isFirstLetterLoweCase, lowercaseFirstLetter, NodeCreator, uppercaseFirstLetter } from "./node.ts";
import { Action } from "./action.ts";
import { VFS } from "./vfs.ts";

export class Root extends NodeCreator {
    private childName: string;
    private services: ts.CallExpression[];
    constructor(basePath?: string) {
        super("Root", basePath);
        this.childName = "";
        this.services = [];
        this.addService(this.name)
    }

    override addChild(child: Action): void {
        if (this.layerDependencies.length != 1) {
            this.childName = child.name;
            const relativePath = createRelativeImportPath(this.path(), child.path());
            // class names must start with an uppercase letter
            const value = isFirstLetterLoweCase(this.childName) ? { value: this.childName, as: uppercaseFirstLetter(this.childName) } : this.childName
            this.addImport(relativePath, value, this.childName + "Live")
            this.addLayerDependency(uppercaseFirstLetter(this.childName));
            this.addService(this.childName);
            this.addLayerBody();
        } else {
            console.log("Root node can only have one child");
        }
    }

    addService(serviceName: string) {
        this.services.push(createService(serviceName));
    }

    override addLayerBody(): void {
        this.layerBody = createRootLayerBody(this.name, this.childName);
    }

    override addLayer(): void {
        const program = createProgram(this.services);
        this.layer = createLayer(this.name, this.layerDependencies, this.layerBody, program);
    }
}

const createProgram = (services: ts.CallExpression[]) => {
    const program = factory.createVariableStatement(
        [factory.createToken(ts.SyntaxKind.ExportKeyword)],
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
                                    [
                                        factory.createVariableStatement(
                                            undefined,
                                            factory.createVariableDeclarationList(
                                                [factory.createVariableDeclaration(
                                                    factory.createIdentifier("root"),
                                                    undefined,
                                                    undefined,
                                                    factory.createYieldExpression(
                                                        factory.createToken(ts.SyntaxKind.AsteriskToken),
                                                        factory.createIdentifier("Root")
                                                    )
                                                )],
                                                ts.NodeFlags.Const
                                            )
                                        ),
                                        factory.createExpressionStatement(factory.createYieldExpression(
                                            factory.createToken(ts.SyntaxKind.AsteriskToken),
                                            factory.createCallExpression(
                                                factory.createPropertyAccessExpression(
                                                    factory.createIdentifier("root"),
                                                    factory.createIdentifier("update")
                                                ),
                                                undefined,
                                                []
                                            )
                                        ))
                                    ],
                                    true
                                )
                            )]
                        ),
                        factory.createIdentifier("pipe")
                    ),
                    undefined,
                    [
                        ...services,
                        factory.createPropertyAccessExpression(
                            factory.createIdentifier("Effect"),
                            factory.createIdentifier("runPromise")
                        )
                    ]
                )
            )],
            ts.NodeFlags.Const
        )
    )
    return program;
}

const createRootLayerBody = (layerName: string, childName: string) => {
    const rootBody = [
        factory.createVariableStatement(
            undefined,
            factory.createVariableDeclarationList(
                [factory.createVariableDeclaration(
                    factory.createIdentifier("proto"),
                    undefined,
                    undefined,
                    factory.createObjectLiteralExpression(
                        [
                            factory.createPropertyAssignment(
                                factory.createIdentifier("status"),
                                factory.createPropertyAccessExpression(
                                    factory.createIdentifier("Status"),
                                    factory.createIdentifier("READY")
                                )
                            ),
                            factory.createPropertyAssignment(
                                factory.createIdentifier("update"),
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
                                                [
                                                    factory.createVariableStatement(
                                                        undefined,
                                                        factory.createVariableDeclarationList(
                                                            [factory.createVariableDeclaration(
                                                                factory.createIdentifier("updateOrFail"),
                                                                undefined,
                                                                undefined,
                                                                factory.createYieldExpression(
                                                                    factory.createToken(ts.SyntaxKind.AsteriskToken),
                                                                    factory.createCallExpression(
                                                                        factory.createPropertyAccessExpression(
                                                                            factory.createIdentifier("Effect"),
                                                                            factory.createIdentifier("either")
                                                                        ),
                                                                        undefined,
                                                                        [factory.createCallExpression(
                                                                            factory.createPropertyAccessExpression(
                                                                                factory.createIdentifier(lowercaseFirstLetter(childName)),
                                                                                factory.createIdentifier("update")
                                                                            ),
                                                                            undefined,
                                                                            []
                                                                        )]
                                                                    )
                                                                )
                                                            )],
                                                            ts.NodeFlags.Const
                                                        )
                                                    ),
                                                    factory.createIfStatement(
                                                        factory.createCallExpression(
                                                            factory.createPropertyAccessExpression(
                                                                factory.createIdentifier("Either"),
                                                                factory.createIdentifier("isLeft")
                                                            ),
                                                            undefined,
                                                            [factory.createIdentifier("updateOrFail")]
                                                        ),
                                                        factory.createBlock(
                                                            [
                                                                factory.createExpressionStatement(factory.createCallExpression(
                                                                    factory.createPropertyAccessExpression(
                                                                        factory.createIdentifier("console"),
                                                                        factory.createIdentifier("log")
                                                                    ),
                                                                    undefined,
                                                                    [
                                                                        factory.createStringLiteral(layerName + " Failed because:"),
                                                                        factory.createPropertyAccessExpression(
                                                                            factory.createPropertyAccessExpression(
                                                                                factory.createIdentifier("updateOrFail"),
                                                                                factory.createIdentifier("left")
                                                                            ),
                                                                            factory.createIdentifier("msg")
                                                                        )
                                                                    ]
                                                                )),
                                                                factory.createExpressionStatement(factory.createBinaryExpression(
                                                                    factory.createPropertyAccessExpression(
                                                                        factory.createIdentifier("proto"),
                                                                        factory.createIdentifier("status")
                                                                    ),
                                                                    factory.createToken(ts.SyntaxKind.EqualsToken),
                                                                    factory.createPropertyAccessExpression(
                                                                        factory.createIdentifier("Status"),
                                                                        factory.createIdentifier("FAILED")
                                                                    )
                                                                )),
                                                                factory.createReturnStatement(factory.createPropertyAccessExpression(
                                                                    factory.createIdentifier("proto"),
                                                                    factory.createIdentifier("status")
                                                                ))
                                                            ],
                                                            true
                                                        ),
                                                        factory.createBlock(
                                                            [
                                                                factory.createExpressionStatement(factory.createBinaryExpression(
                                                                    factory.createPropertyAccessExpression(
                                                                        factory.createIdentifier("proto"),
                                                                        factory.createIdentifier("status")
                                                                    ),
                                                                    factory.createToken(ts.SyntaxKind.EqualsToken),
                                                                    factory.createPropertyAccessExpression(
                                                                        factory.createIdentifier("updateOrFail"),
                                                                        factory.createIdentifier("right")
                                                                    )
                                                                )),
                                                                factory.createReturnStatement(factory.createPropertyAccessExpression(
                                                                    factory.createIdentifier("proto"),
                                                                    factory.createIdentifier("status")
                                                                ))
                                                            ],
                                                            true
                                                        )
                                                    )
                                                ],
                                                true
                                            )
                                        )]
                                    )
                                )
                            )
                        ],
                        true
                    )
                )],
                ts.NodeFlags.Const
            )
        ),
        factory.createReturnStatement(factory.createIdentifier("proto")),
    ];
    return rootBody;
}

const createService = (serviceName: string) => {
    const service = factory.createCallExpression(
        factory.createPropertyAccessExpression(
            factory.createIdentifier("Effect"),
            factory.createIdentifier("provide")
        ),
        undefined,
        [factory.createIdentifier(serviceName + "Live")]
    )
    return service;
}

export class RootBuilder extends Effect.Service<RootBuilder>()(
    "RootBuilder",
    {
        effect: Effect.gen(function*() {
            const vfs = yield* VFS;
            const root = new Root("./dist/src/");

            const buildRoot = () => {
                root.addImport("effect", "Context", "Data", "Effect", "Either", "Layer");
                root.addImport(createRelativeImportPath(root.path(), "./dist/src/types.ts"), "Status")
                root.addError();
                root.addContext();
                root.addLayer();
                vfs.set(root.path(), root.print())
            }
            return {
                root: root,
                buildRoot: buildRoot
            };
        })
    }
) { }
