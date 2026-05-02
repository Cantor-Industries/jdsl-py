import ts, { factory } from "typescript";

type Platform = "bun" | "deno";

const createBaselineCommand = (name: string, options: string[], commandFunction: ts.ArrowFunction) => {
    const optionsPropertyAssignments: ts.ShorthandPropertyAssignment[] = [];
    const optionsBindingElements: ts.BindingElement[] = [];

    options.forEach(option => {
        optionsPropertyAssignments.push(factory.createShorthandPropertyAssignment(
            factory.createIdentifier(option),
            undefined
        ));
        optionsBindingElements.push(factory.createBindingElement(
            undefined,
            undefined,
            factory.createIdentifier(option),
            undefined
        ));
    })

    const command = factory.createVariableStatement(
        undefined,
        factory.createVariableDeclarationList(
            [factory.createVariableDeclaration(
                factory.createIdentifier("command"),
                undefined,
                undefined,
                factory.createCallExpression(
                    factory.createPropertyAccessExpression(
                        factory.createIdentifier("Command"),
                        factory.createIdentifier("make")
                    ),
                    undefined,
                    [
                        factory.createStringLiteral(name),
                        factory.createObjectLiteralExpression(
                            optionsPropertyAssignments,
                            false
                        ),
                        commandFunction
                    ]
                )
            )],
            ts.NodeFlags.Const
        )
    )
    return command;
}

const createOptionalMatch = (name: string) => {
    const optionName = name + "Result";
    const optionalParam = factory.createVariableStatement(
        undefined,
        factory.createVariableDeclarationList(
            [factory.createVariableDeclaration(
                factory.createIdentifier(optionName),
                undefined,
                undefined,
                factory.createCallExpression(
                    factory.createPropertyAccessExpression(
                        factory.createIdentifier("Option"),
                        factory.createIdentifier("match")
                    ),
                    undefined,
                    [
                        factory.createIdentifier(name),
                        factory.createObjectLiteralExpression(
                            [
                                factory.createPropertyAssignment(
                                    factory.createIdentifier("onNone"),
                                    factory.createArrowFunction(
                                        undefined,
                                        undefined,
                                        [],
                                        undefined,
                                        factory.createToken(ts.SyntaxKind.EqualsGreaterThanToken),
                                        factory.createIdentifier("undefined")
                                    )
                                ),
                                factory.createPropertyAssignment(
                                    factory.createIdentifier("onSome"),
                                    factory.createArrowFunction(
                                        undefined,
                                        undefined,
                                        [factory.createParameterDeclaration(
                                            undefined,
                                            undefined,
                                            factory.createIdentifier("opt"),
                                            undefined,
                                            undefined,
                                            undefined
                                        )],
                                        undefined,
                                        factory.createToken(ts.SyntaxKind.EqualsGreaterThanToken),
                                        factory.createIdentifier("opt")
                                    )
                                )
                            ],
                            true
                        )
                    ]
                )
            )],
            ts.NodeFlags.Const
        )
    )
    return { optionalParam, optionName } as const;
}

const createCommandWithoutOptionalParams = (name: string, options: string[]) => {
    const optionsBindingElements: ts.BindingElement[] = [];
    const optionsArgumentArray: ts.Identifier[] = [];

    options.forEach(option => {
        optionsBindingElements.push(factory.createBindingElement(
            undefined,
            undefined,
            factory.createIdentifier(option),
            undefined
        ));
        optionsArgumentArray.push(factory.createIdentifier(option))
    })

    const commandFunction = factory.createArrowFunction(
        undefined,
        undefined,
        [factory.createParameterDeclaration(
            undefined,
            undefined,
            factory.createObjectBindingPattern(optionsBindingElements),
            undefined,
            undefined,
            undefined
        )],
        undefined,
        factory.createToken(ts.SyntaxKind.EqualsGreaterThanToken),
        factory.createCallExpression(
            factory.createIdentifier("program"),
            undefined,
            optionsArgumentArray
        )
    )
    return createBaselineCommand(name, options, commandFunction);
}

const createCommandWithOptionalParams = (name: string, options: { name: string, optional: boolean, restParameter: boolean }[]) => {
    const optionsBindingElements: ts.BindingElement[] = [];
    const optionalParams: ts.VariableStatement[] = [];
    const programArguments: ts.Identifier[] = [];

    options.forEach(option => {
        optionsBindingElements.push(factory.createBindingElement(
            undefined,
            undefined,
            factory.createIdentifier(option.name),
            undefined
        ))

        if (option.optional) {
            const { optionalParam, optionName } = createOptionalMatch(option.name);
            optionalParams.push(optionalParam);
            programArguments.push(factory.createIdentifier(optionName));
        } else {
            programArguments.push(factory.createIdentifier(option.name));
        }
    })

    const commandFunction = factory.createArrowFunction(
        undefined,
        undefined,
        [factory.createParameterDeclaration(
            undefined,
            undefined,
            factory.createObjectBindingPattern(optionsBindingElements),
            undefined,
            undefined,
            undefined
        )],
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
                        ...optionalParams,
                        factory.createReturnStatement(factory.createYieldExpression(
                            factory.createToken(ts.SyntaxKind.AsteriskToken),
                            factory.createCallExpression(
                                factory.createIdentifier("program"),
                                undefined,
                                programArguments
                            )
                        ))
                    ],
                    true
                )
            )]
        )
    )
    return createBaselineCommand(name, options.map(option => option.name), commandFunction);
}

export const createCommandAST = (name: string, options: { name: string, optional: boolean, restParameter: boolean }[], hasOptionalParameter: boolean) => {
    if (hasOptionalParameter) {
        return [createCommandWithOptionalParams(name, options)];
    } else {
        return [createCommandWithoutOptionalParams(name, options.map(option => option.name))];
    }
}

export const createCliAST = (name: string, platform: Platform, pluginNames: string[]) => {
    const platformProviders: (ts.CallExpression | ts.PropertyAccessExpression)[] = [];
    const serviceProviders: ts.CallExpression[] = [factory.createCallExpression(
        factory.createPropertyAccessExpression(
            factory.createIdentifier("Effect"),
            factory.createIdentifier("provide")
        ),
        undefined,
        [factory.createPropertyAccessExpression(
            factory.createIdentifier(name),
            factory.createIdentifier("Default")
        )]
    )];

    if (platform == "bun") {
        platformProviders.push(factory.createCallExpression(
            factory.createPropertyAccessExpression(
                factory.createIdentifier("Effect"),
                factory.createIdentifier("provide")
            ),
            undefined,
            [factory.createPropertyAccessExpression(
                factory.createIdentifier("BunContext"),
                factory.createIdentifier("layer")
            )]
        ))
        platformProviders.push(factory.createCallExpression(
            factory.createPropertyAccessExpression(
                factory.createIdentifier("Effect"),
                factory.createIdentifier("provide")
            ),
            undefined,
            [factory.createCallExpression(
                factory.createPropertyAccessExpression(
                    factory.createIdentifier("CliConfig"),
                    factory.createIdentifier("layer")
                ),
                undefined,
                [factory.createObjectLiteralExpression(
                    [factory.createPropertyAssignment(
                        factory.createIdentifier("showBuiltIns"),
                        factory.createFalse()
                    )],
                    false
                )]
            )]
        ))
        platformProviders.push(factory.createPropertyAccessExpression(
            factory.createIdentifier("BunRuntime"),
            factory.createIdentifier("runMain")
        ))
    } else {
        platformProviders.push(factory.createCallExpression(
            factory.createPropertyAccessExpression(
                factory.createIdentifier("Effect"),
                factory.createIdentifier("provide")
            ),
            undefined,
            [factory.createPropertyAccessExpression(
                factory.createIdentifier("NodeContext"),
                factory.createIdentifier("layer")
            )]
        ))
        platformProviders.push(factory.createCallExpression(
            factory.createPropertyAccessExpression(
                factory.createIdentifier("Effect"),
                factory.createIdentifier("provide")
            ),
            undefined,
            [factory.createCallExpression(
                factory.createPropertyAccessExpression(
                    factory.createIdentifier("CliConfig"),
                    factory.createIdentifier("layer")
                ),
                undefined,
                [factory.createObjectLiteralExpression(
                    [factory.createPropertyAssignment(
                        factory.createIdentifier("showBuiltIns"),
                        factory.createFalse()
                    )],
                    false
                )]
            )]
        ))
        platformProviders.push(factory.createPropertyAccessExpression(
            factory.createIdentifier("NodeRuntime"),
            factory.createIdentifier("runMain")
        ))
    }

    new Set(pluginNames).forEach(plugin => {
        serviceProviders.push(factory.createCallExpression(
            factory.createPropertyAccessExpression(
                factory.createIdentifier("Effect"),
                factory.createIdentifier("provide")
            ),
            undefined,
            [factory.createPropertyAccessExpression(
                factory.createIdentifier(plugin),
                factory.createIdentifier("Default")
            )]
        ))
    })

    const cli = factory.createVariableStatement(
        undefined,
        factory.createVariableDeclarationList(
            [factory.createVariableDeclaration(
                factory.createIdentifier("cli"),
                undefined,
                undefined,
                factory.createCallExpression(
                    factory.createPropertyAccessExpression(
                        factory.createIdentifier("Command"),
                        factory.createIdentifier("run")
                    ),
                    undefined,
                    [
                        factory.createIdentifier("command"),
                        factory.createObjectLiteralExpression(
                            [
                                factory.createPropertyAssignment(
                                    factory.createIdentifier("name"),
                                    factory.createStringLiteral(name)
                                ),
                                factory.createPropertyAssignment(
                                    factory.createIdentifier("version"),
                                    factory.createStringLiteral("0.10")
                                )
                            ],
                            true
                        )
                    ]
                )
            )],
            ts.NodeFlags.Const
        )
    )

    const runner = factory.createExpressionStatement(factory.createCallExpression(
        factory.createPropertyAccessExpression(
            factory.createCallExpression(
                factory.createIdentifier("cli"),
                undefined,
                [factory.createPropertyAccessExpression(
                    factory.createIdentifier("process"),
                    factory.createIdentifier("argv")
                )]
            ),
            factory.createIdentifier("pipe")
        ),
        undefined,
        [
            factory.createCallExpression(
                factory.createPropertyAccessExpression(
                    factory.createIdentifier("Effect"),
                    factory.createIdentifier("catchAll")
                ),
                undefined,
                [factory.createArrowFunction(
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
                    factory.createCallExpression(
                        factory.createPropertyAccessExpression(
                            factory.createIdentifier("Effect"),
                            factory.createIdentifier("succeed")
                        ),
                        undefined,
                        [factory.createCallExpression(
                            factory.createPropertyAccessExpression(
                                factory.createIdentifier("error"),
                                factory.createIdentifier("toString")
                            ),
                            undefined,
                            []
                        )]
                    )
                )]
            ),
            ...serviceProviders,
            ...platformProviders
        ]
    ))
    return [cli, runner];
}