// Rember to explore Effect.firstSuccessOf
import ts, { factory } from "typescript";
import { Effect } from "effect"
import { createLayerDependency, Dependency, lowercaseFirstLetter, NodeCreator } from "./node.ts";
import { VFS } from "./vfs.ts";
import { Action } from "./action.ts";
import { Sequence } from "./sequence.ts";

export class Selector extends NodeCreator {
    private dependencyNames: string[];
    constructor(name: string, basepath?: string) {
        super(name, basepath);
        this.args = factory.createArrayLiteralExpression();
        this.dependencyNames = [];
    }

    addArgs(args: ts.ArrayLiteralExpression) {
        this.args = args;
    }

    override addChild(child: Action | Sequence | Selector): void {
      super.addChild(child);
    }

    override addLayer(): void {
        this.layer = createSelectorLayer(this.name, this.layerBody, this.dependencies);
    }

    override addLayerBody(): void {
        this.layerBody = createSelectorLayerBody(this.dependencies);
    }

    override addLayerDependency(dependencyName: string): void {
        super.addLayerDependency(dependencyName);
        this.dependencyNames.push(dependencyName);
    }
}

export class SelectorBuilder extends Effect.Service<SelectorBuilder>()(
    "SelectorBuilder",
    {
        effect: Effect.gen(function* () {
            console.log("SELECTORBUILDER INIT");
            const vfs = yield* VFS;

            const currentSelector: Selector[] = [];
            const selectors: Map<string, Selector> = new Map();
            let count = 0;

            const buildSelector = () => {
                addSelector("selector_" + count, "./dist/selectors/");
                count += 1;
                addImport("effect", "Data", "Effect");
                selector().addError();
                addLayer();

                vfs.set(selector().path(), selector().print());
            };
            const addChild = (child: Action | Sequence | Selector) => {
                selector().addChild(child);
                vfs.set(selector().path(), selector().print());
            }
            const addImport = (packageName: string, ...values: string[]) => {
                selector().addImport(packageName, ...values)
            };
            const addLayer = () => {
                selector().addLayer();
            };
            const addSelector = (name: string, basePath: string) => {
                const selector = new Selector(name, basePath);
                currentSelector.push(selector);
                selectors.set(name, selector);
            };
            const pop = () => currentSelector.pop();
            const selector = () => {
                const sel = currentSelector.at(-1);
                if (sel) {
                    return sel;
                }
                throw new Error("Selector Map Empty");


            };
            return { addChild, buildSelector, pop, selector } as const;
        })
    }
) { }

const createSelectorLayer = (layerName: string, body: ts.Statement[], dependencies: Dependency[]) => {
    const serviceElements: ts.Expression[] = [];
    const services = factory.createArrayLiteralExpression(serviceElements);
    const dependencyNames = dependencies.map(dep => dep.name);
    const layerDependencies = dependencyNames.map(dep => createLayerDependency(dep))

    dependencyNames.forEach(depName => {
        serviceElements.push(
            factory.createPropertyAccessExpression(
                factory.createIdentifier(depName),
                factory.createIdentifier("Default")
            )
        )
    })

    const layer = [
        factory.createClassDeclaration(
            [factory.createToken(ts.SyntaxKind.ExportKeyword)],
            factory.createIdentifier(layerName),
            undefined,
            [factory.createHeritageClause(
                ts.SyntaxKind.ExtendsKeyword,
                [factory.createExpressionWithTypeArguments(
                    factory.createCallExpression(
                        factory.createCallExpression(
                            factory.createPropertyAccessExpression(
                                factory.createIdentifier("Effect"),
                                factory.createIdentifier("Service")
                            ),
                            [factory.createTypeReferenceNode(
                                factory.createIdentifier(layerName),
                                undefined
                            )],
                            []
                        ),
                        undefined,
                        [
                            factory.createStringLiteral(layerName),
                            factory.createObjectLiteralExpression(
                                [
                                    factory.createPropertyAssignment(
                                        factory.createIdentifier("effect"),
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
                                                    [...layerDependencies, ...body],
                                                    true
                                                )
                                            )]
                                        )
                                    ),
                                    factory.createPropertyAssignment(
                                        factory.createIdentifier("dependencies"),
                                        services,
                                    )
                                ],
                                true
                            )
                        ]
                    ),
                    undefined
                )]
            )],
            []
        ),
    ];
    return layer;
}

const createSelectorLayerBody = (dependencies: Dependency[]) => {
    const updateBody: ts.Statement[] = [];
    const dependencyNames = dependencies.map(dep => dep.name);
    const callParameters = dependencies.map(dep => dep.callParameters)[0];
    const declarationParameters = dependencies.map(dep => dep.declarationParameters)[0];

    if (dependencyNames.length === 1) {
        const dependencyName = lowercaseFirstLetter(dependencyNames[0]);
        updateBody.push(
            factory.createReturnStatement(factory.createYieldExpression(
                factory.createToken(ts.SyntaxKind.AsteriskToken),
                factory.createCallExpression(
                    factory.createPropertyAccessExpression(
                        factory.createIdentifier(dependencyName),
                        factory.createIdentifier("update")
                    ),
                    undefined,
                    callParameters
                )
            ))
        )
    } else {
        dependencyNames.forEach(dependencyName => {
            updateBody.push(
                factory.createReturnStatement(factory.createYieldExpression(
                    factory.createToken(ts.SyntaxKind.AsteriskToken),
                    factory.createCallExpression(
                        factory.createPropertyAccessExpression(
                            factory.createIdentifier(dependencyName),
                            factory.createIdentifier("update")
                        ),
                        undefined,
                        callParameters
                    )
                ))
            )
        })
    }

    const SelectorBody = [
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
                                    [...updateBody],
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
    ];
    return SelectorBody;
}
