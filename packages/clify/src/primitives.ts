import ts, { factory } from "typescript";

type Primitive = "text" | "float" | "boolean";
const createPrimitiveAST = (text: string, type: Primitive, optional: boolean, restParameter: boolean) => {
    let ast: ts.VariableStatement;
    const extraOptions: ts.PropertyAccessExpression[] = [];

    if (optional) {
        extraOptions.push(factory.createPropertyAccessExpression(
            factory.createIdentifier("Options"),
            factory.createIdentifier("optional")
        ))
    }
    if (restParameter) {
        extraOptions.push(factory.createPropertyAccessExpression(
            factory.createIdentifier("Options"),
            factory.createIdentifier("repeated")
        ))
    }

    if (optional || restParameter) {
        ast = factory.createVariableStatement(
            undefined,
            factory.createVariableDeclarationList(
                [factory.createVariableDeclaration(
                    factory.createIdentifier(text),
                    undefined,
                    undefined,
                    factory.createCallExpression(
                        factory.createPropertyAccessExpression(
                            factory.createCallExpression(
                                factory.createPropertyAccessExpression(
                                    factory.createIdentifier("Options"),
                                    factory.createIdentifier(type)
                                ),
                                undefined,
                                [factory.createStringLiteral(text)]
                            ),
                            factory.createIdentifier("pipe")
                        ),
                        undefined,
                        extraOptions
                    )
                )],
                ts.NodeFlags.Const
            )
        )
    } else {
        ast = factory.createVariableStatement(
            undefined,
            factory.createVariableDeclarationList(
                [factory.createVariableDeclaration(
                    factory.createIdentifier(text),
                    undefined,
                    undefined,
                    factory.createCallExpression(
                        factory.createPropertyAccessExpression(
                            factory.createIdentifier("Options"),
                            factory.createIdentifier(type)
                        ),
                        undefined,
                        [factory.createStringLiteral(text)]
                    )
                )],
                ts.NodeFlags.Const
            )
        )
    }

    return ast;
}

export const createStringAST = (text: string, optional: boolean, restParameter: boolean) => {
    return createPrimitiveAST(text, "text", optional, restParameter);
}

export const createNumericAST = (text: string, optional: boolean, restParameter: boolean) => {
    return createPrimitiveAST(text, "float", optional, restParameter);
}

export const createBooleanAST = (text: string, optional: boolean, restParameter: boolean) => {
    return createPrimitiveAST(text, "boolean", optional, restParameter);
}