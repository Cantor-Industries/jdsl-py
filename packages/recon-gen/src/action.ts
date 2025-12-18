import { NodeCreator } from "./utils.ts";
import ts, { factory } from "typescript";

export class Action extends NodeCreator {
    // deno-lint-ignore no-explicit-any
    private args: any[];
    private runFunction: ts.PropertyAssignment[];

    constructor(name: string, basePath ?: string) {
        super(name, basePath);
        this.args = [];
        this.runFunction = [];
    }

    addRunFunction(run: ts.ArrowFunction) {
        this.runFunction.push(createRunFunction(run));
    }

    override addLayerBody(): void {
        this.layerBody = createActonLayerBody(this.name, this.runFunction[0]);
    }
};
export class ActionMap {
    private lastAction: string;
    private actions: Map<string, Action>;
    private agentTree: Map<string, ts.ArrowFunction>;

    constructor(agentTree: Map<string, ts.ArrowFunction>) {
        this.actions = new Map<string, Action>();
        this.lastAction = "";
        this.agentTree = agentTree;
    }

    addAction(name: string, basePath ?: string) {
        this.lastAction = name;
        this.actions.set(name, new Action(name, basePath));
    }

    addImport(packageName: string, ...values: string[]) {
        this.actions.get(this.lastAction)?.addImport(packageName, ...values)
    }

    addContext() {
        this.actions.get(this.lastAction)?.addContext();
        this.actions.get(this.lastAction)?.addError();
    }

    addLayer() {
        const run = this.agentTree.get(this.lastAction.replace("Action", ""));
        if (!run) {
            throw new Error(this.lastAction + "missing matching agent function)")
        }
        this.actions.get(this.lastAction)?.addRunFunction(run);
        this.actions.get(this.lastAction)?.addLayerBody();
    }

    action() {
        const result = this.actions.get(this.lastAction);
        if (result) {
            return result;
        }
        throw new Error("Action Map Empty");
    }

    print() {
        for (const action of this.actions) {
            action[1].print()
        }
    }
}

const createRunFunction = (agentFunction: ts.ArrowFunction) => {
    const runFunction = factory.createPropertyAssignment(
        factory.createIdentifier("run"),
        agentFunction
    );
    return runFunction;
}
const createActonLayerBody = (layerName: string, actionFunction: ts.PropertyAssignment) => {
    const actionLayerBody = [
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
                            actionFunction,
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
                                                [factory.createTryStatement(
                                                    factory.createBlock(
                                                        [
                                                            factory.createExpressionStatement(factory.createCallExpression(
                                                                factory.createPropertyAccessExpression(
                                                                    factory.createIdentifier("proto"),
                                                                    factory.createIdentifier("run")
                                                                ),
                                                                undefined,
                                                                []
                                                            )),
                                                            factory.createReturnStatement(factory.createYieldExpression(
                                                                factory.createToken(ts.SyntaxKind.AsteriskToken),
                                                                factory.createCallExpression(
                                                                    factory.createPropertyAccessExpression(
                                                                        factory.createIdentifier("Effect"),
                                                                        factory.createIdentifier("succeed")
                                                                    ),
                                                                    undefined,
                                                                    [factory.createPropertyAccessExpression(
                                                                        factory.createIdentifier("proto"),
                                                                        factory.createIdentifier("status")
                                                                    )]
                                                                )
                                                            ))
                                                        ],
                                                        true
                                                    ),
                                                    factory.createCatchClause(
                                                        factory.createVariableDeclaration(
                                                            factory.createIdentifier("error"),
                                                            undefined,
                                                            factory.createKeywordTypeNode(ts.SyntaxKind.UnknownKeyword),
                                                            undefined
                                                        ),
                                                        factory.createBlock(
                                                            [
                                                                factory.createIfStatement(
                                                                    factory.createBinaryExpression(
                                                                        factory.createIdentifier("error"),
                                                                        factory.createToken(ts.SyntaxKind.InstanceOfKeyword),
                                                                        factory.createIdentifier("Error")
                                                                    ),
                                                                    factory.createBlock(
                                                                        [factory.createReturnStatement(factory.createYieldExpression(
                                                                            factory.createToken(ts.SyntaxKind.AsteriskToken),
                                                                            factory.createNewExpression(
                                                                                factory.createIdentifier(layerName + "Error"),
                                                                                undefined,
                                                                                [factory.createObjectLiteralExpression(
                                                                                    [factory.createPropertyAssignment(
                                                                                        factory.createIdentifier("msg"),
                                                                                        factory.createPropertyAccessExpression(
                                                                                            factory.createIdentifier("error"),
                                                                                            factory.createIdentifier("message")
                                                                                        )
                                                                                    )],
                                                                                    false
                                                                                )]
                                                                            )
                                                                        ))],
                                                                        true
                                                                    ),
                                                                    undefined
                                                                ),
                                                                factory.createExpressionStatement(factory.createBinaryExpression(
                                                                    factory.createPropertyAccessExpression(
                                                                        factory.createIdentifier("proto"),
                                                                        factory.createIdentifier("status")
                                                                    ),
                                                                    factory.createToken(ts.SyntaxKind.EqualsToken),
                                                                    factory.createAsExpression(
                                                                        factory.createStringLiteral("failed"),
                                                                        factory.createTypeReferenceNode(
                                                                            factory.createQualifiedName(
                                                                                factory.createIdentifier(layerName),
                                                                                factory.createIdentifier("Status")
                                                                            ),
                                                                            undefined
                                                                        )
                                                                    )
                                                                )),
                                                                factory.createReturnStatement(factory.createYieldExpression(
                                                                    factory.createToken(ts.SyntaxKind.AsteriskToken),
                                                                    factory.createNewExpression(
                                                                        factory.createIdentifier(layerName + "Error"),
                                                                        undefined,
                                                                        [factory.createObjectLiteralExpression(
                                                                            [factory.createPropertyAssignment(
                                                                                factory.createIdentifier("msg"),
                                                                                factory.createStringLiteral("Unknown Error has occured")
                                                                            )],
                                                                            false
                                                                        )]
                                                                    )
                                                                ))
                                                            ],
                                                            true
                                                        )
                                                    ),
                                                    undefined
                                                )],
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
    ]
    return actionLayerBody;
}
