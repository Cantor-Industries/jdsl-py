import ts, { factory } from "typescript";
import { Effect } from "effect"
import { createLayerDependency, createRelativeImportPath, Dependency, isFirstLetterLoweCase, lowercaseFirstLetter, NodeCreator, uppercaseFirstLetter } from "./node.ts";
import { VFS } from "./vfs.ts";
import { Action } from "./action.ts";

export class Sequence extends NodeCreator {
    public args: ts.ArrayLiteralExpression;
    private childName: string;
    public dependencies: Dependency[];
    private dependencyNames: string[];
    public callParameters: ts.Identifier[];
    public declarationParameters: ts.ParameterDeclaration[];

    constructor(name: string, basepath?: string) {
        super(name, basepath);
        this.childName = "";
        this.args = factory.createArrayLiteralExpression();
        this.dependencies = [];
        this.dependencyNames = [];
        this.callParameters = [];
        this.declarationParameters = [];
    }

    addArgs(args: ts.ArrayLiteralExpression) {
        this.args = args;
    }

    override addChild(child: Action | Sequence): void {
        console.log("Inside", this.name, "adding", child.name, "as a child")
        if (this.layerDependencies.length === 0) {
            console.log("First child detected!");
            this.childName = child.name;
            const relativePath = createRelativeImportPath(this.path(), child.path());
            // class names imports must start with an uppercase letter
            const value = isFirstLetterLoweCase(this.childName) ? { value: this.childName, as: uppercaseFirstLetter(this.childName) } : this.childName;
            this.addImport(relativePath, value);
            this.addLayerDependency(uppercaseFirstLetter(this.childName));

            this.args = child.args;
            this.callParameters = child.callParameters;
            this.declarationParameters = child.declarationParameters;

            this.dependencies.push({
                name: uppercaseFirstLetter(this.childName),
                callParameters: child.callParameters,
                declarationParameters: child.declarationParameters
            })
            this.addLayerBody();
            this.update();
        }
    }

    override addLayer(): void {
        // this.layer = createSequenceLayer(this.name, this.layerDependencies, this.layerBody, this.dependencyNames);
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

export class SequenceBuilder extends Effect.Service<SequenceBuilder>()(
    "SequenceBuilder",
    {
        effect: Effect.gen(function* () {
            console.log("SEQUENCEBUILDER INIT");
            const vfs = yield* VFS;

            const currentSequence: Sequence[] = [];
            const sequences: Map<string, Sequence> = new Map();
            let count = 0;

            const buildSequence = () => {
                addSequence("sequence_" + count, "./dist/sequences/");
                count += 1;
                addImport("effect", "Data", "Effect");
                // proto.addImport(createRelativeImportPath(proto.sequence().path(), "./dist/types.ts"), "Status");
                sequence().addError();
                addLayer();

                vfs.set(sequence().path(), sequence().print());
            };
            const addChild = (child: Action | Sequence) => {
                sequence().addChild(child);
                vfs.set(sequence().path(), sequence().print());
            }
            const addImport = (packageName: string, ...values: string[]) => {
                sequence().addImport(packageName, ...values)
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
            return { addChild,  buildSequence, pop, sequence } as const;
        })
    }
) { }