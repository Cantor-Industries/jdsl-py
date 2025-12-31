import ts, { ArrayLiteralExpression, ArrowFunction, factory } from "typescript";
import { generateFactoryCode } from "./factorycodegen.ts"
import { NodeCreator } from "./utils.ts";

export class Action extends NodeCreator {
    private args: ts.ArrayLiteralExpression;
    private runFunction: ts.PropertyAssignment[];

    constructor(name: string, basePath?: string) {
        super(name, basePath);
        this.args = factory.createArrayLiteralExpression();
        this.runFunction = [];
    }

    addArgs(args: ts.ArrayLiteralExpression) {
        this.args = args;
    }

    addRunFunction(run: ts.ArrowFunction) {
        this.runFunction.push(createRunFunction(run));
    }

    override addLayerBody(): void {
        // console.log(this.args.getText())
        this.layerBody = createActonLayerBody(this.name, this.runFunction[0], this.args);
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

    addAction(name: string, basePath?: string) {
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
        this.actions.get(this.lastAction)!.addRunFunction(run);
        this.actions.get(this.lastAction)!.addLayerBody();
    }

    addArgs(args: ts.ArrayLiteralExpression) {
        this.actions.get(this.lastAction)?.addArgs(args);
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
    const sourceText = agentFunction.getText();
    const sourcefile = ts.createSourceFile("code.ts", sourceText, ts.ScriptTarget.ESNext, true);
    const targetText = generateFactoryCode(ts, sourcefile).slice(38, -5); // remove the parent expression
    const arrowFunction = eval(targetText) as ArrowFunction;
    const runFunction = factory.createPropertyAssignment(
        factory.createIdentifier("run"),
        arrowFunction
    );
    return runFunction;
}
const createActonLayerBody = (layerName: string, actionFunction: ts.PropertyAssignment, args?: ts.ArrayLiteralExpression) => {
    let values: ts.Expression[] = [];

    if (args) {
        const sourceText = args.getText();
        const sourcefile = ts.createSourceFile("code.ts", sourceText, ts.ScriptTarget.ESNext, true);
        const targetText = generateFactoryCode(ts, sourcefile).slice(38, -5); // remove the parent expression
        const arrayLiteral = eval(targetText) as ArrayLiteralExpression;
        values = [...arrayLiteral.elements]
    }
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
                                factory.createPropertyAccessExpression(
                                    factory.createIdentifier("Status"),
                                    factory.createIdentifier("FAILED")
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
                                                                [...values]
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
                                                                    factory.createPropertyAccessExpression(
                                                                        factory.createIdentifier("Status"),
                                                                        factory.createIdentifier("FAILED")
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
