import { posix } from "node:path"
import ts, { Node, factory } from "typescript";

export class NodeCreator {
  public name: string;
  protected basePath: string
  private sourceFile: ts.SourceFile;
  private importList: ts.ImportDeclaration[];
  private context: (ts.VariableStatement | ts.ClassDeclaration)[];
  protected layer: (ts.VariableStatement | ts.ClassDeclaration)[];
  protected layerDependencies: ts.VariableStatement[];
  protected layerBody: ts.Statement [];
  private namespace: ts.ModuleDeclaration[];
  private taggedError: (ts.VariableStatement | ts.ClassDeclaration)[];

  constructor(name: string, basePath?: string) {
    this.name = name;
    this.basePath = basePath ?? "";
    this.sourceFile = ts.createSourceFile(this.path(), "", ts.ScriptTarget.ESNext, true);
    this.importList = [];
    this.context = [];
    this.layer = [];
    this.layerDependencies = [];
    this.layerBody = [];
    this.namespace = [];
    this.taggedError = [];
  }

  addImport(packageName: string, ...values: (string | { value: string, as: string })[]) {
    const imports = createImport(packageName, ...values);
    this.importList.push(imports);
  }

  // deno-lint-ignore no-explicit-any
  addChild(child: any) {
    // method must be overriden
    child;
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

  update() {
    this.layer = createLayer(this.name, this.layerDependencies, this.layerBody);
    this.sourceFile = ts.createSourceFile(this.name + ".ts", this.compile(), ts.ScriptTarget.Latest, true);
  }

  path() {
    return this.basePath + this.name + ".ts";
  }

  print() {
    this.update();
    return this.sourceFile.getText();
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

const createImport = (packageName: string, ...values: (string | { value: string, as: string })[]): ts.ImportDeclaration => {
  const namedImports = [];
  for (const namedImport of values) {
    if (typeof namedImport == "string") {
      namedImports.push(factory.createImportSpecifier(
        false,
        undefined,
        factory.createIdentifier(namedImport)
      ))
    } else {
      namedImports.push(factory.createImportSpecifier(
        false,
        factory.createIdentifier(namedImport.value),
        factory.createIdentifier(namedImport.as)
      ))
    }
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

export function createRelativeImportPath(from: string, to: string): string {
  const fromDir = posix.dirname(from);
  let relativePath = posix.relative(fromDir, to);

  if (!relativePath.startsWith(".")) {
    relativePath = "./" + relativePath;
  }

  return relativePath;
}

export const createLayer = (layerName: string, dependencies: ts.VariableStatement[], body: ts.Statement [], ...other: ts.VariableStatement[]) => {
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
                      factory.createIdentifier("sync")
                    ),
                    undefined,
                    [factory.createArrowFunction(
                      undefined,
                      undefined,
                      [],
                      undefined,
                      factory.createToken(ts.SyntaxKind.EqualsGreaterThanToken),
                      factory.createBlock(
                        [...dependencies, ...body],
                        true
                      )
                    )]
                  )
                )],
                true
              )
            ]
          ),
          undefined
        )]
      )],
      []
    )
    ,
    ...other,
  ];
  return layer;
}

// export const createLayer = (layerName: string, dependencies: ts.VariableStatement[], body: (ts.VariableStatement | ts.ReturnStatement)[], ...other: ts.VariableStatement[]) => {
//   const layer = [
//     factory.createVariableStatement(
//       [factory.createToken(ts.SyntaxKind.ExportKeyword)],
//       factory.createVariableDeclarationList(
//         [factory.createVariableDeclaration(
//           factory.createIdentifier(layerName + "Live"),
//           undefined,
//           undefined,
//           factory.createCallExpression(
//             factory.createPropertyAccessExpression(
//               factory.createIdentifier("Layer"),
//               factory.createIdentifier("effect")
//             ),
//             undefined,
//             [
//               factory.createIdentifier(layerName),
//               factory.createCallExpression(
//                 factory.createPropertyAccessExpression(
//                   factory.createIdentifier("Effect"),
//                   factory.createIdentifier("gen")
//                 ),
//                 undefined,
//                 [factory.createFunctionExpression(
//                   undefined,
//                   factory.createToken(ts.SyntaxKind.AsteriskToken),
//                   undefined,
//                   undefined,
//                   [],
//                   undefined,
//                   factory.createBlock(
//                     [...dependencies, ...body],
//                     true
//                   )
//                 )]
//               )
//             ]
//           )
//         )],
//         ts.NodeFlags.Const
//       )
//     ),
//     ...other,
//   ];
//   return layer;
// }

const createNamespace = (layerName: string): ts.ModuleDeclaration => {
  const nmspace = factory.createModuleDeclaration(
    [
      factory.createToken(ts.SyntaxKind.ExportKeyword),
      factory.createToken(ts.SyntaxKind.DeclareKeyword)
    ],
    factory.createIdentifier(layerName),
    factory.createModuleBlock([
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
  if (text.startsWith("\"")) {
    return text.slice(1, text.length - 1)
  }
  return text;
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

export const isFirstLetterLoweCase = (text: string): boolean => {
  if (!text) {
    return false;
  }
  const firstLetter = text.charAt(0);
  const lowerCaseFirstLetter = lowercaseFirstLetter(text).charAt(0);
  if (firstLetter === lowerCaseFirstLetter) {
    return true;
  }
  return false;
}

export const uppercaseFirstLetter = (text: string): string => {
  if (!text) {
    return "";
  }
  return text.charAt(0).toUpperCase() + text.slice(1);
}