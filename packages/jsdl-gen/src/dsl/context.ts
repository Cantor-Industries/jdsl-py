import ts, { factory, type Expression } from "typescript";
import { Effect } from "effect";
import { type ImportClause, type PluginBody } from "./node.ts";

type Keys = "system" | "message";
type MessageKeys = "role" | "content";

export class ContextBuilder extends Effect.Service<ContextBuilder>()(
    "ContextBuilder",
    {
        effect: Effect.gen(function* () {
            let isInitialized: boolean = false;
            const createImport = () => {
                const moduleSpecifier = "@jdsl/provider/context";
                const importClause: ImportClause = {
                    namedBindings: [{ name: "ContextWindow", isType: false }]
                }
                isInitialized = true;
                return { moduleSpecifier, importClause } as const;
            }

            const createBeforeExpression = (data: Map<Keys, string | Map<MessageKeys, string>>) => {
                const systemInstructions = data.get("system");
                const messageInstructions = data.get("message");

                const contextBody: ts.PropertyAssignment[] = [];

                if (systemInstructions && typeof systemInstructions === "string") {
                    const system = factory.createPropertyAssignment(
                        factory.createIdentifier("system"),
                        factory.createStringLiteral(systemInstructions)
                    )
                    contextBody.push(system);
                }
                if (messageInstructions) {
                    let message: ts.PropertyAssignment[] = []
                    if (typeof messageInstructions === "string") {
                        message = [
                            factory.createPropertyAssignment(
                                factory.createIdentifier("role"),
                                factory.createStringLiteral("user")
                            ),
                            factory.createPropertyAssignment(
                                factory.createIdentifier("content"),
                                factory.createStringLiteral(messageInstructions)
                            )
                        ]
                    } else {
                        message = [
                            factory.createPropertyAssignment(
                                factory.createIdentifier("role"),
                                factory.createStringLiteral(messageInstructions.get("role")!)
                            ),
                            factory.createPropertyAssignment(
                                factory.createIdentifier("content"),
                                factory.createStringLiteral(messageInstructions.get("content")!)
                            )
                        ]
                    }
                    contextBody.push(factory.createPropertyAssignment(
                        factory.createIdentifier("message"),
                        factory.createObjectLiteralExpression(message, false)
                    ))
                }
                const contextExpression = factory.createExpressionStatement(
                    factory.createBinaryExpression(
                        factory.createIdentifier("yield"),
                        factory.createToken(ts.SyntaxKind.AsteriskToken),
                        factory.createCallExpression(
                            factory.createPropertyAccessExpression(
                                factory.createIdentifier("contextWindow"),
                                factory.createIdentifier("push")
                            ),
                            undefined,
                            [factory.createObjectLiteralExpression(contextBody, false)]
                        )
                    )
                );
                return { position: "before", expression: contextExpression } as const;
                
            }

            const createAfterExpression = (data: Map<Keys, string | Map<MessageKeys, string>>) => {
                const contextExpression = factory.createExpressionStatement(
                    factory.createBinaryExpression(
                        factory.createIdentifier("yield"),
                        factory.createToken(ts.SyntaxKind.AsteriskToken),
                        factory.createCallExpression(
                            factory.createPropertyAccessExpression(
                                factory.createIdentifier("contextWindow"),
                                factory.createIdentifier("pop")
                            ),
                            undefined,
                            undefined
                        )
                    )
                )
                return { position: "after", expression: contextExpression} as const;
            }

            const createBody = (context: ts.ObjectLiteralExpression) => {
                const data: Map<Keys, string | Map<MessageKeys, string>> = new Map();
                context.forEachChild((child) => {
                    if (ts.isPropertyAssignment(child)) {
                        const key = child.name;
                        const value = child.initializer;

                        if (ts.isIdentifier(key) && key.text === "system" && ts.isStringLiteral(value)) {
                            data.set("system", value.text);
                        }
                        if (ts.isIdentifier(key) && key.text === "message") {
                            if (ts.isStringLiteral(value)) {
                                data.set("message", value.text);
                            } else if (ts.isObjectLiteralExpression(value)) {
                                const message: Map<MessageKeys, string> = new Map();
                                value.forEachChild(child => {
                                    if (ts.isPropertyAssignment(child)) {
                                        const key = child.name;
                                        const value = child.initializer;

                                        if (ts.isIdentifier(key) && key.text === "role" && ts.isStringLiteral(value)) {
                                            message.set("role", value.text);
                                        }

                                        if (ts.isIdentifier(key) && key.text === "content" && ts.isStringLiteral(value)) {
                                            message.set("content", value.text);
                                        }
                                    }
                                })
                                data.set("message", message)
                            }
                        }
                    }
                })

                const beforeBody = createBeforeExpression(data);
                const afterBody = createAfterExpression(data);
                const pluginBody = [beforeBody, afterBody];
                return pluginBody;
            }

            return { createBody, createImport, isInitialized } as const;
        })
    }
) { }