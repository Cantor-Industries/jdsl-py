import ts, { factory, Node } from "typescript";
import { getEscapedText, NodeCreator } from "./node.ts";
import { Effect } from "effect/index";
import { Tools } from "./transform.ts";
import { VFS } from "./vfs.ts";
import { ReconLanguageServer } from "./lsp.ts";
import { generateFactoryCode } from "./factorycodegen.ts";
import { layer } from "@effect/platform/Etag";

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
        const result = createArrowFunction(this.name, run);
        this.runFunction.push(result.runFunction);
        this.callParameters = result.callParameters;
        this.declarationParameters = result.declarationParameters
    }

    override addLayerBody(): void {
        this.layerBody = createActonLayerBody(this.runFunction[0], this.callParameters, this.declarationParameters);
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

const createArrowFunction = (layerName: string, agentFunction: ts.ArrowFunction) => {
    const declarationParameters: ts.ParameterDeclaration[] = agentFunction.parameters.map(param => param);

    function hasAsyncModifier(fn: ts.ArrowFunction): boolean {
        return !!fn.modifiers?.some(m => m.kind === ts.SyntaxKind.AsyncKeyword);
    }

    function normalizeToBlock(body: ts.ConciseBody): ts.Block {
        if (ts.isBlock(body)) {
            return body;
        }

        return ts.factory.createBlock(
            [ts.factory.createReturnStatement(body)],
            true
        );
    }

    function removeAwaitExpressions(block: ts.Block): ts.Block {
        const visitor = (node: ts.Node): ts.Node => {
            if (ts.isAwaitExpression(node)) {
                return ts.visitNode(node.expression, visitor);
            }

            return ts.visitEachChild(node, visitor, undefined);
        };

        return ts.visitNode(block, visitor) as ts.Block;
    }

    const isAsync = hasAsyncModifier(agentFunction);
    const factoryFunction = eval(generateFactoryCode(ts, agentFunction)) as ts.ArrowFunction
    let block = normalizeToBlock(factoryFunction.body);

    if (isAsync) {
        block = removeAwaitExpressions(block);
    }

    const innerArrowFunction = factory.createArrowFunction(
        undefined,
        undefined,
        [],
        undefined,
        factory.createToken(ts.SyntaxKind.EqualsGreaterThanToken),
        block
    )

    const effectFullCall =
        factory.createCallExpression(
            factory.createPropertyAccessExpression(
                factory.createIdentifier("Effect"),
                factory.createIdentifier(isAsync ? "tryPromise" : "try"),
            ),
            undefined,
            [factory.createObjectLiteralExpression(
                [
                    factory.createPropertyAssignment(
                        factory.createIdentifier("try"),
                        innerArrowFunction
                    ),
                    factory.createPropertyAssignment(
                        factory.createIdentifier("catch"),
                        factory.createParenthesizedExpression(factory.createArrowFunction(
                            undefined,
                            undefined,
                            [factory.createParameterDeclaration(
                                undefined,
                                undefined,
                                factory.createIdentifier("error"),
                                undefined,
                                undefined,
                                undefined
                            )],
                            undefined,
                            factory.createToken(ts.SyntaxKind.EqualsGreaterThanToken),
                            factory.createBlock(
                                [
                                    factory.createIfStatement(
                                        factory.createBinaryExpression(
                                            factory.createIdentifier("error"),
                                            factory.createToken(ts.SyntaxKind.InstanceOfKeyword),
                                            factory.createIdentifier("Error")
                                        ),
                                        factory.createBlock(
                                            [
                                                factory.createExpressionStatement(factory.createCallExpression(
                                                    factory.createPropertyAccessExpression(
                                                        factory.createIdentifier("console"),
                                                        factory.createIdentifier("error")
                                                    ),
                                                    undefined,
                                                    [
                                                        factory.createStringLiteral(layerName + "failed because:"),
                                                        factory.createPropertyAccessExpression(
                                                            factory.createIdentifier("error"),
                                                            factory.createIdentifier("message")
                                                        )
                                                    ]
                                                )),
                                                factory.createReturnStatement(factory.createNewExpression(
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
                                                ))
                                            ],
                                            true
                                        ),
                                        undefined
                                    ),
                                    factory.createReturnStatement(factory.createNewExpression(
                                        factory.createIdentifier(layerName + "Error"),
                                        undefined,
                                        [factory.createObjectLiteralExpression(
                                            [factory.createPropertyAssignment(
                                                factory.createIdentifier("msg"),
                                                factory.createStringLiteral("Unknown Error has occured")
                                            )],
                                            false
                                        )]
                                    ))
                                ],
                                true
                            )
                        ))
                    )
                ],
                true
            )]
        )

    const effectFullArrowFunction = factory.updateArrowFunction(
        agentFunction,
        undefined,
        agentFunction.typeParameters,
        agentFunction.parameters,
        agentFunction.type, agentFunction.equalsGreaterThanToken,
        effectFullCall
    )

    const runFunction = factory.createVariableStatement(
        undefined,
        factory.createVariableDeclarationList(
            [factory.createVariableDeclaration(
                factory.createIdentifier("run"),
                undefined,
                undefined,
                effectFullArrowFunction
            )],
            ts.NodeFlags.Const
        )
    )
    const parameters = agentFunction.parameters;
    const callParameters = parameters.map(param => param.getChildAt(0) as ts.Identifier);

    return { runFunction, declarationParameters, callParameters };
}

const createActonLayerBody = (actionFunction: ts.VariableStatement, callParameters: ts.Identifier[], declarationParameters: ts.ParameterDeclaration[]) => {

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
                                    [factory.createReturnStatement(factory.createBinaryExpression(
                                        factory.createIdentifier("yield"),
                                        factory.createToken(ts.SyntaxKind.AsteriskToken),
                                        factory.createCallExpression(
                                            factory.createIdentifier("run"),
                                            undefined,
                                            callParameters
                                        )
                                    ))],
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
