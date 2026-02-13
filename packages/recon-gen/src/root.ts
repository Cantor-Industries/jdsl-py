import ts, { factory } from "typescript";
import { Effect } from "effect";
import { createRelativeImportPath, type Dependency, isFirstLetterLoweCase, lowercaseFirstLetter, NodeCreator, uppercaseFirstLetter } from "./node.ts";
import { Action } from "./action.ts";
import { VFS } from "./vfs.ts";
import { generateFactoryCode } from "./factorycodegen.ts";
import { Sequence } from "./sequence.ts";
import { Selector } from "./selector.ts";
import { ReconLanguageServer } from "./lsp.ts";

export class Root extends NodeCreator {
    private dependencyName: string;
    constructor(name: string, basePath?: string) {
        super(name, basePath);
        this.dependencyName = "";
        this.args = factory.createArrayLiteralExpression();
    }

  override addChild(child: Action | Sequence | Selector, pipeable?: boolean): void {
    if (this.layerDependencies.length != 1) {
      console.log("Inside", this.name, "adding", child.name, "as a child")
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
        declarationParameters: child.declarationParameters,
        pipeable: pipeable ?? true
      })
      this.addLayerBody();
      this.update();
    } else {
      console.log("Root node can only have one child");
    }
  }

    override addLayerBody(): void {
        this.layerBody = createRootLayerBody(this.name, this.args, this.dependencies);
    }

    override addLayerDependency(dependencyName: string): void {
        super.addLayerDependency(dependencyName);
        this.dependencyName = dependencyName;
    }

    override addLayer(): void {
        this.layer = createRootLayer(this.name, this.layerDependencies, this.layerBody, this.dependencyName);
    }
}

export class RootBuilder extends Effect.Service<RootBuilder>()(
    "RootBuilder",
    {
        effect: Effect.gen(function* () {
            const vfs = yield* VFS;
            const languageServer = yield* ReconLanguageServer;
            const rootList: Root[] = [];

            const buildRoot = (name?: string) => {
                const root = new Root("Root", "./dist/");
                root.name = name ?? "Root";
                root.name = root.name === "root" ? "Root" : root.name;
                root.addImport("effect", "Data", "Effect", "Either");
                root.addError();
                root.addLayer();
                vfs.set(root.path(), root.print());
                languageServer.getSyntacticDiagnostics(root.path());
                rootList.push(root);
            }
            const addChild = (child: Action | Sequence | Selector) => {
                const curRoot = root();
                curRoot.addChild(child);
                vfs.set(curRoot.path(), curRoot.print());
                languageServer.getSyntacticDiagnostics(curRoot.path());
            }

            const root = () => {
                const root = rootList.at(-1);
                if (root) {
                    return root;
                }
                throw new Error("No Root Node Defined yet");
            }
            return { root, buildRoot, addChild } as const;
        })
    }
) { }

const createRootLayer = (layerName: string, dependencies: ts.VariableStatement[], body: ts.Statement[], dependencyName: string) => {
    const services = factory.createArrayLiteralExpression(
        [
            factory.createPropertyAccessExpression(
                factory.createIdentifier(dependencyName),
                factory.createIdentifier("Default")
            )]
    );

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
                                [factory.createPropertyAssignment(
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

const createRootLayerBody = (layerName: string, args: ts.ArrayLiteralExpression, dependencies: Dependency[]) => {
    const dependencyName = dependencies.map(dep => dep.name)[0];    
    const callParameters = dependencies.map(dep => dep.callParameters)[0];
    const declarationParameters = dependencies.map(dep => dep.declarationParameters)[0];    
    let values: ts.Expression[] = [];
    let argsProvided = false;

    if (args.elements.length != 0) {
        argsProvided = true;
        const targetText = generateFactoryCode(ts, args)
        const arrayLiteral = eval(targetText) as ts.ArrayLiteralExpression;
        values = [...arrayLiteral.elements]
    } else {
        values
    }

    const rootBody = [
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
                        argsProvided ? [] : declarationParameters!,
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
                                        factory.createVariableStatement(
                                            undefined,
                                            factory.createVariableDeclarationList(
                                                [factory.createVariableDeclaration(
                                                    factory.createIdentifier("updateOrFail"),
                                                    undefined,
                                                    undefined,
                                                    factory.createYieldExpression(
                                                        factory.createToken(ts.SyntaxKind.AsteriskToken),
                                                        factory.createCallExpression(
                                                            factory.createPropertyAccessExpression(
                                                                factory.createIdentifier("Effect"),
                                                                factory.createIdentifier("either")
                                                            ),
                                                            undefined,
                                                            [factory.createCallExpression(
                                                                factory.createPropertyAccessExpression(
                                                                    factory.createIdentifier(lowercaseFirstLetter(dependencyName!)),
                                                                    factory.createIdentifier("update")
                                                                ),
                                                                undefined,
                                                                argsProvided ? values : callParameters
                                                            )]
                                                        )
                                                    )
                                                )],
                                                ts.NodeFlags.Const
                                            )
                                        ),
                                        factory.createIfStatement(
                                            factory.createCallExpression(
                                                factory.createPropertyAccessExpression(
                                                    factory.createIdentifier("Either"),
                                                    factory.createIdentifier("isLeft")
                                                ),
                                                undefined,
                                                [factory.createIdentifier("updateOrFail")]
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
                                                            factory.createStringLiteral("Root Failed because:"),
                                                            factory.createPropertyAccessExpression(
                                                                factory.createPropertyAccessExpression(
                                                                    factory.createIdentifier("updateOrFail"),
                                                                    factory.createIdentifier("left")
                                                                ),
                                                                factory.createIdentifier("msg")
                                                            )
                                                        ]
                                                    )),
                                                    factory.createReturnStatement(factory.createYieldExpression(
                                                        factory.createToken(ts.SyntaxKind.AsteriskToken),
                                                        factory.createNewExpression(
                                                            factory.createIdentifier(layerName + "Error"),
                                                            undefined,
                                                            [factory.createObjectLiteralExpression(
                                                                [factory.createPropertyAssignment(
                                                                    factory.createIdentifier("msg"),
                                                                    factory.createPropertyAccessExpression(
                                                                        factory.createPropertyAccessExpression(
                                                                            factory.createIdentifier("updateOrFail"),
                                                                            factory.createIdentifier("left")
                                                                        ),
                                                                        factory.createIdentifier("msg")
                                                                    )
                                                                )],
                                                                false
                                                            )]
                                                        )
                                                    ))
                                                ],
                                                true
                                            ),
                                            factory.createBlock(
                                                [factory.createReturnStatement(factory.createPropertyAccessExpression(
                                                    factory.createIdentifier("updateOrFail"),
                                                    factory.createIdentifier("right")
                                                ))],
                                                true
                                            )
                                        ),
                                    ],
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
    return rootBody;
}
