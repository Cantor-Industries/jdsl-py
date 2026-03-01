import ts, { factory } from "typescript";
import { Effect } from "effect"
import { createLayerDependency, type Dependency, type ImportClause, lowercaseFirstLetter, NodeCreator } from "./node.ts";
import { VFS } from "../lsp/vfs.ts";
import { Action } from "./action.ts";
import { Selector } from "./selector.ts";
import { ReconLanguageServer } from "../lsp/lsp.ts";

export class Sequence extends NodeCreator {
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
        this.layer = createSequenceLayer(this.name, this.layerBody, this.dependencies);
    }

    override addLayerBody(): void {
        this.layerBody = createSequenceLayerBody(this.dependencies);
    }

    override addLayerDependency(dependencyName: string): void {
        super.addLayerDependency(dependencyName);
        this.dependencyNames.push(dependencyName);
    }
}

export class SequenceBuilder extends Effect.Service<SequenceBuilder>()(
    "SequenceBuilder",
    {
        effect: Effect.gen(function* () {
            const vfs = yield* VFS;
            const languageServer = yield* ReconLanguageServer;

            const currentSequence: Sequence[] = [];
            const sequences: Map<string, Sequence> = new Map();
            let count = 0;

            const buildSequence = () => {
                addSequence("sequence_" + count, "./dist/sequences/");
                count += 1;
                const importClause: ImportClause = {
                    phaseModifier: false,
                    namedBindings: [
                        { name: "Data", isType: false },
                        { name: "Effect", isType: false },
                    ]
                }
                addImport("effect", importClause);
                sequence().addError();
                addLayer();

                vfs.set(sequence().path(), sequence().print());
                languageServer.getSyntacticDiagnostics(sequence().path());
            };
            const addChild = (child: Action | Sequence | Selector) => {
                sequence().addChild(child);
                vfs.set(sequence().path(), sequence().print());
                languageServer.getSyntacticDiagnostics(sequence().path());
            };

            const addImport = (moduleSpecifier: string, importClause: ImportClause) => {
                sequence().addImport(moduleSpecifier, importClause)
            };
            const addLayer = () => {
                sequence().addLayer();
            };
            const addSequence = (name: string, basePath: string) => {
                const sequence = new Sequence(name, basePath);
                currentSequence.push(sequence);
                sequences.set(name, sequence);
            };
            const pop = () => currentSequence.pop();
            const sequence = () => {
                const seq = currentSequence.at(-1);
                if (seq) {
                    return seq;
                }
                throw new Error("Sequence Map Empty");


            };
            return { addChild, buildSequence, pop, sequence } as const;
        })
    }
) { }

const createSequenceLayer = (layerName: string, body: ts.Statement[], dependencies: Dependency[]) => {
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

const createSequenceLayerBody = (dependencies: Dependency[]) => {
    if (!dependencies || dependencies.length === 0) {
        throw new Error("Dependencies Array Cannot be Zero");
    }
    const updateBody: ts.Statement[] = [];
    const declarationParameters: ts.ParameterDeclaration[] = dependencies[0]!.declarationParameters;

    let childCount = 0;
    for (const dependency of dependencies) {
        const statement = factory.createVariableStatement(
            undefined,
            factory.createVariableDeclarationList(
                [factory.createVariableDeclaration(
                    factory.createIdentifier("step_" + childCount),
                    undefined,
                    undefined,
                    factory.createBinaryExpression(
                        factory.createIdentifier("yield"),
                        factory.createToken(ts.SyntaxKind.AsteriskToken),
                        factory.createCallExpression(
                            factory.createPropertyAccessExpression(
                                factory.createIdentifier(lowercaseFirstLetter(dependency.name)),
                                factory.createIdentifier("update")
                            ),
                            undefined,
                            childCount === 0 ? dependency.callParameters : [factory.createIdentifier("step_" + (childCount - 1))]
                        )
                    )
                )],
                ts.NodeFlags.Const
            )
        );
        childCount += 1;
        updateBody.push(statement)

    }
    updateBody.push(factory.createReturnStatement(factory.createIdentifier("step_" + (childCount - 1))))

    const sequenceBody = [
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
    return sequenceBody;
}
