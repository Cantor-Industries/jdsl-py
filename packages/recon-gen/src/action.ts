import ts, { ArrowFunction, factory, Node } from "typescript";
import { generateFactoryCode } from "./factorycodegen.ts"
import { createRelativeImportPath, getEscapedText, NodeCreator } from "./node.ts";
import { Effect } from "effect/index";
import { Tools } from "./transform.ts";
import { ReconLanguageServer } from "./lsp.ts";
import { normalize, VFS } from "./vfs.ts";
import { Root } from "./root.ts";
import { Sequence } from "./sequence.ts";

export class Action extends NodeCreator {
    public args: ts.ArrayLiteralExpression;
    public callParameters: ts.Identifier[];
    public declarationParameters: ts.ParameterDeclaration[];
    private runFunction: ts.VariableStatement[];

    constructor(name: string, basePath?: string) {
        super(name, basePath);
        this.args = factory.createArrayLiteralExpression();
        this.runFunction = [];
        this.callParameters = [];
        this.declarationParameters = [];
    }

    addArgs(args: ts.ArrayLiteralExpression) {
        this.args = args;
    }

    addRunFunction(run: ts.ArrowFunction) {
        const result = createRunFunction(run);
        this.runFunction.push(result.runFunction);
        this.callParameters = result.callParameters;
        this.declarationParameters = result.declarationParameters
    }

    override addLayerBody(): void {
        this.layerBody = createActonLayerBody(this.name, this.runFunction[0], this.callParameters);
    }
};

export class ActionBuilder extends Effect.Service<ActionBuilder>()(
    "ActionBuilder",
    {
        effect: Effect.gen(function* () {
            console.log("ACTIONBUILDER INIT");
            const toolService = yield* Tools;
            const vfs = yield* VFS;
            const languageService = yield* ReconLanguageServer;

            let currentAction: Action | undefined;
            const actions: Map<string, Action> = new Map()

            const buildAction = (skill: Map<string, Node>, parent: Root | Sequence) => {
                const action = skill.get("call");
                if (!action) {
                    console.error("Action must have a call attribute");
                    return
                }
                if (actions.has(getEscapedText(action) + "Action")) {
                    console.log(getEscapedText(action) + "Action already exists, exiting");
                    return;
                }
                proto.addAction(getEscapedText(action) + "Action", "./dist/actions/");
                proto.addImport("effect", "Data", "Effect");
                // proto.addImport(createRelativeImportPath(proto.action().path(), "./dist/types.ts"), "Status");
                proto.action().addError();

                const args = skill.get("args");
                if (args && ts.isArrayLiteralExpression(args)) {
                    proto.addArgs(args)
                }
                proto.addLayer();
                parent.addChild(proto.action());
                vfs.set(proto.action().path(), proto.action().print());
                vfs.set(parent.path(), parent.print());
            }

            const proto = {
                addAction: (name: string, basePath?: string) => {
                    const action = new Action(name, basePath);
                    currentAction = action;
                    actions.set(name, action);
                },
                action: () => {
                    if (currentAction) {
                        return currentAction;
                    }
                    throw new Error("Action Map Empty");
                },
                addImport: (packageName: string, ...values: string[]) => {

                    proto.action().addImport(packageName, ...values)
                },
                addContext: () => {
                    proto.action().addContext();
                    proto.action().addError();
                },
                addLayer: () => {
                    const run = toolService.tools.get(proto.action().name.replace("Action", ""));
                    if (!run) {
                        throw new Error(` ${currentAction?.name} missing matching agent function)`)
                    }
                    proto.action().addRunFunction(run);
                    proto.action().addLayerBody();
                },
                addArgs: (args: ts.ArrayLiteralExpression) => {
                    proto.action().addArgs(args);
                },
                buildAction: buildAction,
                getActions: () => {
                    return actions;
                },
                print: () => {
                    for (const action of actions) {
                        action[1].print()
                    }
                }
            }
            return proto;
        }),
    }
) { }

export class ActionMap {
    private currentAction: string;
    private actions: Map<string, Action>;
    private agentTree: Map<string, ts.ArrowFunction>;

    constructor(agentTree: Map<string, ts.ArrowFunction>) {
        this.actions = new Map<string, Action>();
        this.currentAction = "";
        this.agentTree = agentTree;
    }

    addAction(name: string, basePath?: string) {
        this.currentAction = name;
        this.actions.set(name, new Action(name, basePath));
    }

    addImport(packageName: string, ...values: string[]) {
        this.action().addImport(packageName, ...values)
    }

    addContext() {
        this.action().addContext();
        this.action().addError();
    }

    addLayer() {
        const run = this.agentTree.get(this.currentAction.replace("Action", ""));
        if (!run) {
            throw new Error(this.currentAction + " missing matching agent function)")
        }
        this.action().addRunFunction(run);
        this.action().addLayerBody();
    }

    addArgs(args: ts.ArrayLiteralExpression) {
        this.action().addArgs(args);
    }

    action() {
        const result = this.actions.get(this.currentAction);
        if (result) {
            return result;
        }
        throw new Error("Action Map Empty");
    }

    getActions() {
        return this.actions;
    }

    print() {
        for (const action of this.actions) {
            action[1].print()
        }
    }
}

const createRunFunction = (agentFunction: ts.ArrowFunction) => {
    const arrowFunction = eval(generateFactoryCode(ts, agentFunction)) as ArrowFunction;
    let declarationParameters: ts.ParameterDeclaration[] = [];

    const extractParameters = (node: ts.Node): ts.Node => {
        if (ts.isArrowFunction(node)) {
            const parameterString = "[" + node.parameters.map(param => generateFactoryCode(ts, param)) + "]";
            declarationParameters = eval(parameterString)

            return node;
        }
        return node.forEachChild(extractParameters)!;
    }

    
    const runFunction = factory.createVariableStatement(
        undefined,
        factory.createVariableDeclarationList(
            [factory.createVariableDeclaration(
                factory.createIdentifier("run"),
                undefined,
                undefined,
                arrowFunction
            )],
            ts.NodeFlags.Const
        )
    )
    extractParameters(agentFunction);
    const parameters = agentFunction.parameters;
    const callParameters = parameters.map(param => eval(generateFactoryCode(ts, param.getChildAt(0))) as ts.Identifier);

    return { runFunction, declarationParameters, callParameters };
}

const createActonLayerBody = (layerName: string, actionFunction: ts.VariableStatement, params: ts.Identifier[]) => {
    // const parameters = params;
    let parameters: ts.ParameterDeclaration[] = [];

    const extractParameters = (node: ts.Node): ts.Node => {
        if (ts.isArrowFunction(node)) {
            const parameterString = "[" + node.parameters.map(param => generateFactoryCode(ts, param)) + "]";
            parameters = eval(parameterString)

            return node;
        }
        return node.forEachChild(extractParameters)!;
    }

    extractParameters(actionFunction);

    const actionLayerBody = [
        actionFunction,
        // factory.createVariableDeclarationList(
        //     [factory.createVariableDeclaration(
        //         factory.createIdentifier("status"),
        //         undefined,
        //         factory.createTypeReferenceNode(
        //             factory.createIdentifier("Status"),
        //             undefined
        //         ),
        //         factory.createPropertyAccessExpression(
        //             factory.createIdentifier("Status"),
        //             factory.createIdentifier("READY")
        //         )
        //     )],
        //     ts.NodeFlags.Let
        // ),
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
                        parameters,
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
                                                // factory.createExpressionStatement(factory.createCallExpression(
                                                //     factory.createIdentifier("run"),
                                                //     undefined,
                                                //     params,
                                                // )),
                                                factory.createReturnStatement(factory.createCallExpression(
                                                    factory.createIdentifier("run"),
                                                    undefined,
                                                    params,
                                                )),
                                                // factory.createExpressionStatement(factory.createBinaryExpression(
                                                //     factory.createIdentifier("status"),
                                                //     factory.createToken(ts.SyntaxKind.EqualsToken),
                                                //     factory.createPropertyAccessExpression(
                                                //         factory.createIdentifier("Status"),
                                                //         factory.createIdentifier("SUCCESS")
                                                //     )
                                                // )),
                                                // factory.createReturnStatement(factory.createYieldExpression(
                                                //     factory.createToken(ts.SyntaxKind.AsteriskToken),
                                                //     factory.createCallExpression(
                                                //         factory.createPropertyAccessExpression(
                                                //             factory.createIdentifier("Effect"),
                                                //             factory.createIdentifier("succeed")
                                                //         ),
                                                //         undefined,
                                                //         [factory.createIdentifier("status")]
                                                //     )
                                                // ))
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
                                                    // factory.createExpressionStatement(factory.createBinaryExpression(
                                                    //     factory.createIdentifier("status"),
                                                    //     factory.createToken(ts.SyntaxKind.EqualsToken),
                                                    //     factory.createPropertyAccessExpression(
                                                    //         factory.createIdentifier("Status"),
                                                    //         factory.createIdentifier("FAILED")
                                                    //     )
                                                    // )),
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
    ]
    return actionLayerBody as ts.Statement[];
}
