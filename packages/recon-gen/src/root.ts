import ts, { factory } from "typescript";
import { lowercaseFirstLetter, NodeCreator } from "./utils.ts";

export class Root extends NodeCreator {
    private childName: string;
    constructor() {
        super("Root");
        this.childName = "";
    }

    override addChild(childName: string): void {
        if (this.layerDependencies.length != 1) {
            this.childName = childName;
            this.addImport(childName + ".ts", childName, childName + "Live")
            this.addLayerDependency(childName);
            this.addLayerBody();
            this.updateSourceFile();
        } else {
            console.log("Root node can only have one child");
        }
    }

    override addLayerBody(): void {
        this.layerBody = createRootLayerBody(this.name, this.childName);
    }
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
                                factory.createAsExpression(
                                    factory.createStringLiteral("ready"),
                                    factory.createTypeReferenceNode(
                                        factory.createQualifiedName(
                                            factory.createIdentifier(layerName),
                                            factory.createIdentifier("Status")
                                        ),
                                        undefined
                                    )
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
                                                                    factory.createStringLiteral("failed")
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
        factory.createReturnStatement(factory.createIdentifier("proto"))
    ];
    return rootBody;
}
const root = new Root();

export default root;