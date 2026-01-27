import ts, { ArrowFunction, factory, Node } from "typescript";
import { generateFactoryCode } from "./factorycodegen.ts"
import { getEscapedText, NodeCreator } from "./node.ts";
import { Effect } from "effect/index";
import { Tools } from "./transform.ts";
import { VFS } from "./vfs.ts";
import { ReconLanguageServer } from "./lsp.ts";

export class Action extends NodeCreator {
    private runFunction: ts.VariableStatement[];

    constructor(name: string, basePath?: string) {
        super(name, basePath);
        this.args = factory.createArrayLiteralExpression();
        this.runFunction = [];
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
            const languageServer = yield* ReconLanguageServer;

            let currentAction: Action | undefined;
            const actions: Map<string, Action> = new Map()

            const buildAction = (skill: Map<string, Node>) => {
                const call = skill.get("call");
                if (!call) {
                    console.error("Action must have a call attribute");
                    return
                }
                if (actions.has(getEscapedText(call) + "Action")) {
                    console.log(getEscapedText(call) + "Action already exists, exiting");
                    return;
                }
                addAction(getEscapedText(call) + "Action", "./dist/actions/");
                addImport("effect", "Data", "Effect");
                action().addError();

                const args = skill.get("args");
                if (args && ts.isArrayLiteralExpression(args)) {
                    addArgs(args)
                }
                addLayer();
                action().update();
                vfs.set(action().path(), action().print());
                languageServer.getSyntacticDiagnostics(action().path());
            }

            const addAction = (name: string, basePath?: string) => {
                const action = new Action(name, basePath);
                currentAction = action;
                actions.set(name, action);
            }
            const action = () => {
                if (currentAction) {
                    return currentAction;
                }
                throw new Error("Action Map Empty");
            }
            const addImport = (packageName: string, ...values: string[]) => {

                action().addImport(packageName, ...values)
            }
            const addLayer = () => {
                const run = toolService.tools.get(action().name.replace("Action", ""));
                if (!run) {
                    throw new Error(` ${currentAction?.name} missing matching agent function)`)
                }
                action().addRunFunction(run);
                action().addLayerBody();
            }
            const addArgs = (args: ts.ArrayLiteralExpression) => {
                action().addArgs(args);
            }
            return { action, buildAction } as const;
        }),
    }
) { }

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
                                                factory.createReturnStatement(factory.createCallExpression(
                                                    factory.createIdentifier("run"),
                                                    undefined,
                                                    params,
                                                )),
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
