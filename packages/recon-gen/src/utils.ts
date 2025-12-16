import ts, { Node, factory } from "typescript";

export class NodeCreator {
  protected name: string;
  private sourceFile: ts.SourceFile;
  private importList: ts.ImportDeclaration[];
  private context: (ts.VariableStatement | ts.ClassDeclaration)[];
  protected layer: ts.VariableStatement[];
  protected layerDependencies: ts.VariableStatement[];
  protected layerBody: (ts.VariableStatement | ts.ReturnStatement)[];
  private namespace: ts.ModuleDeclaration[];
  private taggedError: (ts.VariableStatement | ts.ClassDeclaration)[];

  constructor(name: string) {
    this.name = name;
    this.sourceFile = ts.createSourceFile(name + ".ts", "", ts.ScriptTarget.ESNext, true);
    this.importList = [];
    this.context = [];
    this.layer = [];
    this.layerDependencies = [];
    this.layerBody = [];
    this.namespace = [];
    this.taggedError = [];
  }

  addImport(packageName: string, ...values: string[]) {
    const imports = createImport(packageName, ...values);
    this.importList.push(imports);
  }

  addChild(childName: string) {
    // method must be overriden
    childName;
  }

  addContext() {
    this.context = [
      ...this.context,
      ...createContext(this.name)
    ];
    this.addNamespace();
  }

  addError() {
    this.taggedError = [
      ...this.taggedError,
      ...createTaggedError(this.name)
    ];
  }

  addLayer() {
    this.addLayerBody();
    this.layer = createLayer(this.name, this.layerDependencies, this.layerBody);
  }

  addLayerDependency(dependencyName: string) {
    const dependency = createLayerDependency(dependencyName);
    this.layerDependencies.push(dependency);
  }

  addLayerBody() {
    this.layerBody = createLayerBody();
  }

  private addNamespace() {
    this.namespace.push(createNamespace(this.name));
  }

  private compile() {
    this.addLayer();
    const nodes = factory.createNodeArray([
      ...this.importList,
      ...this.context,
      ...this.taggedError,
      ...this.namespace,
      ...this.layer
    ]);
    const printer = ts.createPrinter({ newLine: ts.NewLineKind.LineFeed });
    return printer.printList(ts.ListFormat.MultiLine, nodes, this.sourceFile);
  }

  protected updateSourceFile() {
    this.layer = createLayer(this.name, this.layerDependencies, this.layerBody);
    this.sourceFile = ts.createSourceFile(this.name + ".ts", this.compile(), ts.ScriptTarget.Latest, true);
  }

  print() {
    this.updateSourceFile();
    console.log(this.sourceFile.getText());
  }
}

const createLayerBody = () => {
  const layerBobyBlock = [
    factory.createVariableStatement(
      undefined,
      factory.createVariableDeclarationList(
        [factory.createVariableDeclaration(
          factory.createIdentifier("proto"),
          undefined,
          undefined,
          factory.createObjectLiteralExpression(
            [
              factory.createPropertyAssignment(
                factory.createIdentifier("status"),
                factory.createAsExpression(
                  factory.createStringLiteral("ready"),
                  factory.createTypeReferenceNode(
                    factory.createQualifiedName(
                      factory.createIdentifier("Behavior"),
                      factory.createIdentifier("Status")
                    ),
                    undefined
                  )
                )
              ),
              factory.createPropertyAssignment(
                factory.createIdentifier("update"),
                factory.createArrowFunction(
                  undefined,
                  undefined,
                  [],
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
                        [],
                        true
                      )
                    )]
                  )
                )
              )
            ],
            true
          )
        )],
        ts.NodeFlags.Const
      )
    ),
    factory.createReturnStatement(factory.createIdentifier("proto"))
  ];
  return layerBobyBlock;
}

const createContext = (name: string): (ts.VariableStatement | ts.ClassDeclaration)[] => {
  const identifier = factory.createIdentifier(name);
  const tag = factory.createIdentifier(name + "Tag");
  const def = [
    factory.createVariableStatement(
      undefined,
      factory.createVariableDeclarationList(
        [factory.createVariableDeclaration(
          tag,
          undefined,
          undefined,
          factory.createCallExpression(
            factory.createCallExpression(
              factory.createPropertyAccessExpression(
                factory.createIdentifier("Context"),
                factory.createIdentifier("Tag")
              ),
              undefined,
              [factory.createStringLiteral(name)]
            ),
            [
              factory.createTypeReferenceNode(
                identifier,
                undefined
              ),
              factory.createTypeReferenceNode(
                factory.createQualifiedName(
                  factory.createIdentifier(name),
                  factory.createIdentifier("Behavior")
                ),
                undefined
              )
            ],
            []
          )
        )],
        ts.NodeFlags.Const
      )
    ),
    factory.createClassDeclaration(
      [factory.createToken(ts.SyntaxKind.ExportKeyword)],
      identifier,
      undefined,
      [factory.createHeritageClause(
        ts.SyntaxKind.ExtendsKeyword,
        [factory.createExpressionWithTypeArguments(
          tag,
          undefined
        )]
      )],
      []
    )
  ];
  return def
}

const createLayerDependency = (dependencyName: string) => {
  const layerName = lowercaseFirstLetter(dependencyName);
  const dep = factory.createVariableStatement(
    undefined,
    factory.createVariableDeclarationList(
      [factory.createVariableDeclaration(
        factory.createIdentifier(layerName),
        undefined,
        undefined,
        factory.createYieldExpression(
          factory.createToken(ts.SyntaxKind.AsteriskToken),
          factory.createIdentifier(dependencyName)
        )
      )],
      ts.NodeFlags.Const
    )
  )
  return dep;
}

const createImport = (packageName: string, ...values: string[]): ts.ImportDeclaration => {
  const namedImports = [];
  for (const namedImport of values) {
    namedImports.push(factory.createImportSpecifier(
      false,
      undefined,
      factory.createIdentifier(namedImport)
    ))
  }

  const imports = factory.createImportDeclaration(
    undefined,
    factory.createImportClause(
      undefined,
      undefined,
      factory.createNamedImports(namedImports)
    ),
    factory.createStringLiteral(packageName),
    undefined
  );
  return imports;
}

export const createLayer = (layerName: string, dependencies: ts.VariableStatement[], body: (ts.VariableStatement | ts.ReturnStatement)[], ...other: ts.VariableStatement[]) => {
  const layer = [
    factory.createVariableStatement(
      [factory.createToken(ts.SyntaxKind.ExportKeyword)],
      factory.createVariableDeclarationList(
        [factory.createVariableDeclaration(
          factory.createIdentifier(layerName + "Live"),
          undefined,
          undefined,
          factory.createCallExpression(
            factory.createPropertyAccessExpression(
              factory.createIdentifier("Layer"),
              factory.createIdentifier("effect")
            ),
            undefined,
            [
              factory.createIdentifier(layerName),
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
            ]
          )
        )],
        ts.NodeFlags.Const
      )
    ),
    ...other,
  ];
  return layer;
}

const createNamespace = (layerName: string): ts.ModuleDeclaration => {
  const nmspace = factory.createModuleDeclaration(
    [
      factory.createToken(ts.SyntaxKind.ExportKeyword),
      factory.createToken(ts.SyntaxKind.DeclareKeyword)
    ],
    factory.createIdentifier(layerName),
    factory.createModuleBlock([
      factory.createEnumDeclaration(
        [factory.createToken(ts.SyntaxKind.ExportKeyword)],
        factory.createIdentifier("Status"),
        [
          factory.createEnumMember(
            factory.createIdentifier("READY"),
            factory.createStringLiteral("ready")
          ),
          factory.createEnumMember(
            factory.createIdentifier("RUNNING"),
            factory.createStringLiteral("running")
          ),
          factory.createEnumMember(
            factory.createIdentifier("SUCCESS"),
            factory.createStringLiteral("success")
          ),
          factory.createEnumMember(
            factory.createIdentifier("FAILED"),
            factory.createStringLiteral("failed")
          )
        ]
      ),
      factory.createInterfaceDeclaration(
        [factory.createToken(ts.SyntaxKind.ExportKeyword)],
        factory.createIdentifier("Behavior"),
        undefined,
        undefined,
        [
          factory.createPropertySignature(
            undefined,
            factory.createIdentifier("status"),
            undefined,
            factory.createTypeReferenceNode(
              factory.createIdentifier("Status"),
              undefined
            )
          ),
          factory.createPropertySignature(
            undefined,
            factory.createIdentifier("update"),
            undefined,
            factory.createFunctionTypeNode(
              undefined,
              [],
              factory.createTypeReferenceNode(
                factory.createQualifiedName(
                  factory.createIdentifier("Effect"),
                  factory.createIdentifier("Effect")
                ),
                [
                  factory.createTypeReferenceNode(
                    factory.createIdentifier("Status"),
                    undefined
                  ),
                  factory.createTypeReferenceNode(
                    factory.createIdentifier(layerName + "Error"),
                    undefined
                  ),
                  factory.createKeywordTypeNode(ts.SyntaxKind.NeverKeyword)
                ]
              )
            )
          )
        ]
      )
    ]),
    ts.NodeFlags.Namespace
  )
  return nmspace;

}

const createTaggedError = (layername: string) => {
  const taggedError = [
    factory.createVariableStatement(
      undefined,
      factory.createVariableDeclarationList(
        [factory.createVariableDeclaration(
          factory.createIdentifier(layername + "ErrorTag"),
          undefined,
          undefined,
          factory.createExpressionWithTypeArguments(
            factory.createCallExpression(
              factory.createPropertyAccessExpression(
                factory.createIdentifier("Data"),
                factory.createIdentifier("TaggedError")
              ),
              undefined,
              [factory.createStringLiteral(layername + "Error")]
            ),
            [factory.createTypeLiteralNode([factory.createPropertySignature(
              undefined,
              factory.createIdentifier("msg"),
              undefined,
              factory.createKeywordTypeNode(ts.SyntaxKind.StringKeyword)
            )])]
          )
        )],
        ts.NodeFlags.Const
      )
    ),
    factory.createClassDeclaration(
      [factory.createToken(ts.SyntaxKind.ExportKeyword)],
      factory.createIdentifier(layername + "Error"),
      undefined,
      [factory.createHeritageClause(
        ts.SyntaxKind.ExtendsKeyword,
        [factory.createExpressionWithTypeArguments(
          factory.createIdentifier(layername + "ErrorTag"),
          undefined
        )]
      )],
      []
    )
  ]
  return taggedError;
}

export const getEscapedText = (node: Node) => {
  const text = node.getText();
  return text.slice(1, text.length - 1)
}

export const print = (nodes: ts.NodeArray<ts.Node>) => {
  const printer = ts.createPrinter({ newLine: ts.NewLineKind.LineFeed });
  const resultFile = ts.createSourceFile(
    "temp.ts",
    "",
    ts.ScriptTarget.Latest,
    false,
    ts.ScriptKind.TS
  );

  console.log(printer.printList(ts.ListFormat.MultiLine, nodes, resultFile));
}

export const lowercaseFirstLetter = (text: string): string => {
  if (!text) {
    return "";
  }
  return text.charAt(0).toLowerCase() + text.slice(1);
}