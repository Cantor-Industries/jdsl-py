import ts, { factory } from "typescript";
import { Effect } from "effect"
import { createRelativeImportPath, isFirstLetterLoweCase, lowercaseFirstLetter, NodeCreator, uppercaseFirstLetter } from "./node.ts";
import { generateFactoryCode } from "./factorycodegen.ts";
import { VFS } from "./vfs.ts";
import { Root } from "./root.ts";
import { Action } from "./action.ts";

export class Sequence extends NodeCreator {
    public args: ts.ArrayLiteralExpression;
    private childName: string;
    private dependencyNames: string[];
    public callParameters: ts.Identifier[];
    public declarationParameters: ts.ParameterDeclaration[];
    public parent: Root | Sequence;

    constructor(name: string, parent: Root | Sequence, basepath?: string) {
        super(name, basepath);
        this.childName = "";
        this.args = factory.createArrayLiteralExpression();
        this.dependencyNames = [];
        this.callParameters = [];
        this.declarationParameters = [];
        this.parent = parent;
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
            this.addLayerBody();
            this.update()
            console.log(this.name, "parent is", this.parent.name);
            this.parent.addChild(this);
            this.parent.update();
        }
    }

    override addLayer(): void {
        this.layer = createSequenceLayer(this.name, this.layerDependencies, this.layerBody, this.dependencyNames);
    }

    override addLayerBody(): void {
        this.layerBody = createSequenceLayerBody(this.dependencyNames, this.callParameters, this.declarationParameters);
    }

    override addLayerDependency(dependencyName: string): void {
        super.addLayerDependency(dependencyName);
        this.dependencyNames.push(dependencyName);
    }
}

const createSequenceLayer = (layerName: string, dependencies: ts.VariableStatement[], body: ts.Statement[], dependencyNames: string[]) => {
    const serviceElements: ts.Expression[] = [];
    const services = factory.createArrayLiteralExpression(serviceElements);

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
                                                    [...dependencies, ...body],
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

const createSequenceLayerBody = (dependencyNames: string[], callParameters: ts.Identifier[], declarationParameters: ts.ParameterDeclaration[]) => {
    const updateBody: ts.Statement[] = [];

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
    }

    // if (args.elements.length != 0) {
    //     const targetText = generateFactoryCode(ts, args)
    //     const arrayLiteral = eval(targetText) as ts.ArrayLiteralExpression;
    //     values = [...arrayLiteral.elements]
    // }
    // console.log(parameters);

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

            let currentSequence: Sequence;
            const sequences: Map<string, Sequence> = new Map();
            let count = 0;

            const buildSequence = (parent: Root | Sequence) => {
                addSequence("sequence_" + count, parent, "./dist/sequences/");
                count += 1;
                addImport("effect", "Data", "Effect");
                // proto.addImport(createRelativeImportPath(proto.sequence().path(), "./dist/types.ts"), "Status");
                sequence().addError();
                addLayer();

                // parent.addChild(sequence());
                vfs.set(parent.path(), parent.print());
                vfs.set(sequence().path(), sequence().print());
            };
            const updateParent = (parent: Root | Sequence) => {
                parent.addChild(sequence());
                parent.addLayer();
                parent.addLayerBody();
                vfs.set(parent.path(), parent.print());
            };
            const addArgs = (args: ts.ArrayLiteralExpression) => {
                currentSequence?.addArgs(args);
            };
            const addImport = (packageName: string, ...values: string[]) => {
                currentSequence?.addImport(packageName, ...values)
            };
            const addLayer = () => {
                currentSequence?.addLayer();
            };
            const addSequence = (name: string, parent: Root | Sequence, basePath: string) => {
                const sequence = new Sequence(name, parent, basePath);
                currentSequence = sequence;
                sequences.set(name, currentSequence);
            };
            const getSequences = () => sequences
            const sequence = () => {
                if (currentSequence) {
                    return currentSequence;
                }
                throw new Error("Sequence Map Empty");
            };
            return { addArgs, addImport, addLayer, addSequence, buildSequence, getSequences, sequence, updateParent } as const;
        })
    }
) { }