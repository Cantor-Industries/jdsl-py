import ts, { factory } from "typescript";
import { Effect } from "effect";
import { type ImportClause } from "./node.ts";


export class ModelBuilder extends Effect.Service<ModelBuilder>()(
    "ModelBuilder",
    {
        effect: Effect.gen(function* () {
            const createImport = () => {
                const moduleSpecifier = "@jdsl/provider";
                const importClause: ImportClause = {
                    namedBindings: [{ name: "LanguageModel", isType: false }]
                }
                return { moduleSpecifier, importClause } as const;
            }

            const createImports = () => {
                const imports: {specifier: string, clause: ImportClause}[] = [];
                const pluginNames = ["LanguageModel", "ContextWindow", "AiModel", "AiModelConfig", "AiProvider", "ModelsDev", "RoundRobinRouter"];
                
                imports.push({
                    specifier: "@jdsl/provider", clause: {namedBindings: [{name: "LanguageModel", isType: false}]}
                });
                imports.push({
                    specifier: "@jdsl/provider/context", clause: {namedBindings: [{name: "ContextWindow", isType: false}]}
                });                
                imports.push({
                   specifier:  "@jdsl/provider/aimodel", clause: {namedBindings: [{name: "AiModel", isType: false}]}
                });                
                imports.push({
                    specifier:"@jdsl/router/config", clause: {namedBindings: [{name: "AiModelConfig", isType: false}]}
                }); 
                imports.push({
                    specifier: "@jdsl/provider/providers", clause: {namedBindings: [{name: "AiProvider", isType: false}]}
                });                
                imports.push({
                    specifier: "@jdsl/router/models-dev", clause: {namedBindings: [{name: "ModelsDev", isType: false}]}
                });                
                imports.push({
                    specifier: "@jdsl/router", clause: {namedBindings: [{name: "RoundRobinRouter", isType: false}]}
                });    
                
                return { imports, pluginNames };
            }

            const createBeforeExpression = (model: string, provider?: string) => {

                const modelExpression = factory.createExpressionStatement(factory.createBinaryExpression(
                    factory.createIdentifier("yield"),
                    factory.createToken(ts.SyntaxKind.AsteriskToken),
                    factory.createCallExpression(
                        factory.createPropertyAccessExpression(
                            factory.createIdentifier("languageModel"),
                            factory.createIdentifier("chooseModel")
                        ),
                        undefined,
                        [factory.createStringLiteral(model)]
                    )
                ))

                if (provider) {
                    const providerExpression = factory.createExpressionStatement(factory.createBinaryExpression(
                        factory.createIdentifier("yield"),
                        factory.createToken(ts.SyntaxKind.AsteriskToken),
                        factory.createCallExpression(
                            factory.createPropertyAccessExpression(
                                factory.createIdentifier("languageModel"),
                                factory.createIdentifier("chooseProvider")
                            ),
                            undefined,
                            [factory.createStringLiteral(provider)]
                        )
                    ))
                    return [
                        { position: "before", expression: providerExpression},
                        { position: "before", expression: modelExpression}
                    ]
                }

                return [{ position: "before", expression: modelExpression }];

            }

            const createBody = (model: ts.StringLiteral) => {
                const text = model.text.split(":");

                if (text.length == 1) {
                    const modelName = text[0];
                    const beforeBody = createBeforeExpression(modelName!);
                    return beforeBody;
                } else {
                    const providerName = text[0];
                    const modelName = text[1];
                    const beforeBody = createBeforeExpression(modelName!, providerName);
                    return beforeBody;
                }
            }

            return { createBody, createImport, createImports } as const;
        })
    }
) { }