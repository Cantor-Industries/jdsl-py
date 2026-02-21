import ts, { factory, type Node } from "typescript";
import { createRelativeImportPath, getEscapedText, NodeCreator } from "./node.ts";
import { Effect } from "effect/index";
import { Tools } from "./transform.ts";
import { normalize, VFS } from "./vfs.ts";
import { ReconLanguageServer } from "./lsp.ts";
import { generateFactoryCode } from "./factorycodegen.ts";
import { ReconEnvBuilder } from "./env.ts";
import { make } from "effect/Schema";

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
        this.layerBody = createActonLayerBody(this.runFunction[0]!, this.callParameters, this.declarationParameters);
    }
};

export class ActionBuilder extends Effect.Service<ActionBuilder>()(
    "ActionBuilder",
    {
        effect: Effect.gen(function* () {
            const toolService = yield* Tools;
            const vfs = yield* VFS;
            const languageServer = yield* ReconLanguageServer;
            const reconEnv = yield* ReconEnvBuilder;

            let currentAction: Action | undefined;
            const actions: Map<string, Action> = new Map()

            const buildAction = (skill: Map<string, Node>) => {
                const call = skill.get("call");
                if (!call) {
                    throw new Error("Action must have a call attribute");
                }
                const callName = getEscapedText(call);
                if (toolService.tools.get(callName)) {
                    const actionName = getEscapedText(call) + "Action";
                    if (actions.has(actionName)) {
                        console.log(getEscapedText(call) + "Action already exists, exiting");
                        currentAction = actions.get(actionName)
                        return;
                    }
                    addAction(actionName, "./dist/actions/");
                    addImport("effect", undefined, "Data", "Effect");
                    action().addError();

                    const args = skill.get("args");
                    if (args && ts.isArrayLiteralExpression(args)) {
                        addArgs(args)
                    }
                    addLayer();
                    action().update();
                    vfs.set(action().path(), action().print());
                    languageServer.getSyntacticDiagnostics(action().path());
                } else if (reconEnv.checkImport(callName)) {
                    const actionName = callName + "Action";
                    const runFunction = reconEnv.getRunFunction(callName);
                    toolService.tools.set(callName, runFunction);
                    addAction(actionName, "./dist/actions/");
                    addImport("effect", undefined, "Data", "Effect");
                    const localImports = reconEnv.getImport(callName);
                    const packageName = createRelativeImportPath(action().path(), localImports.packageName);
                    const namedImport = localImports.namedBinding?.namedImport;
                    const namedBindings = localImports.namedBinding?.namedBindings;
                    // console.log("Local Imports:", packageName, "->", namedBindings);
                    addImport(packageName, namedImport, ...namedBindings ?? []);
                    action().addError();

                    const args = skill.get("args");
                    if (args && ts.isArrayLiteralExpression(args)) {
                        addArgs(args);
                    }
                    addLayer();
                    action().update();
                    vfs.set(action().path(), action().print());
                    languageServer.getSyntacticDiagnostics(action().path());
                }
                else {
                    throw new Error(`Failed to resolve ${callName})`);
                }

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
            const addImport = (packageName: string, namedImport: string | undefined, ...namedBindings: string[]) => {

                action().addImport(packageName, namedImport,...namedBindings)
            }
            const addLayer = () => {
                const run = toolService.tools.get(action().name.replace("Action", ""));
                if (!run) {
                    throw new Error(` ${currentAction?.name} missing matching agent function)`)
                }
                const actionImports = reconEnv.checkSymbols(run);
                for (const [packageName, packages] of actionImports) {
                    addImport(packageName, packages.namedImport, ...packages.namedBindings)
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

    const isAsync = hasAsyncModifier(agentFunction);
    const factoryFunction = eval(generateFactoryCode(ts, agentFunction)) as ts.ArrowFunction
    const block = normalizeToBlock(factoryFunction.body);

    const innerArrowFunction = factory.createArrowFunction(
        agentFunction.modifiers,
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
