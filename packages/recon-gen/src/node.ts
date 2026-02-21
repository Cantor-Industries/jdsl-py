import { posix } from "path"
import ts, { type Node, factory } from "typescript";
import { Sequence } from "./sequence.ts";
import { Action } from "./action.ts";
import { Selector } from "./selector.ts";

export interface Dependency {
	name: string;
	callParameters: ts.Identifier[];
	declarationParameters: ts.ParameterDeclaration[];
	pipeable: boolean;
}

export class NodeCreator {
	public name: string;
	protected basePath: string
	private sourceFile: ts.SourceFile;
	private importList: Map<string, ts.ImportDeclaration>;
	private context: (ts.VariableStatement | ts.ClassDeclaration)[];
	protected layer: (ts.VariableStatement | ts.ClassDeclaration)[];
	protected layerDependencies: ts.VariableStatement[];
	protected layerBody: ts.Statement[];
	private namespace: ts.ModuleDeclaration[];
	private taggedError: (ts.VariableStatement | ts.ClassDeclaration)[];
	protected dependencies: Dependency[];
	protected childName: string;
	public args: ts.ArrayLiteralExpression;
	public callParameters: ts.Identifier[];
	public declarationParameters: ts.ParameterDeclaration[];
	private firstChild: boolean;

	constructor(name: string, basePath?: string) {
		this.name = name;
		this.basePath = basePath ?? "";
		this.sourceFile = ts.createSourceFile(this.path(), "", ts.ScriptTarget.ESNext, true);
		this.importList = new Map();
		this.context = [];
		this.layer = [];
		this.layerDependencies = [];
		this.layerBody = [];
		this.namespace = [];
		this.taggedError = [];
		this.dependencies = [];
		this.childName = "";
		this.args = factory.createArrayLiteralExpression();
		this.callParameters = [];
		this.declarationParameters = [];
		this.firstChild = true
	}

	addImport(packageName: string, namedImport: string | undefined, ...namedBindings: (string | { value: string, as: string })[]) {
		const imports = createImport(packageName, namedImport, ...namedBindings);
		this.importList.set(packageName, imports);
	}

	protected addChild(child: Action | Sequence | Selector, pipeable?: boolean): void {
		console.log("Inside", this.name, "adding", child.name, "as a child")
		this.childName = child.name;
		const relativePath = createRelativeImportPath(this.path(), child.path());
		// class names imports must start with an uppercase letter
		const value = isFirstLetterLoweCase(this.childName) ? { value: this.childName, as: uppercaseFirstLetter(this.childName) } : this.childName;
		this.addImport(relativePath, undefined, value);
		this.addLayerDependency(uppercaseFirstLetter(this.childName));

		if (this.firstChild) {
			this.firstChild = false;
			this.args = child.args;
			this.callParameters = child.callParameters;
			this.declarationParameters = child.declarationParameters;
		}

		this.dependencies.push({
			name: uppercaseFirstLetter(this.childName),
			callParameters: child.callParameters,
			declarationParameters: child.declarationParameters,
			pipeable: pipeable ?? true
		})
		this.addLayerBody();
		this.update();
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
		const imports: ts.ImportDeclaration[] = [];
		this.importList.forEach(imprt => imports.push(imprt));
		const nodes = factory.createNodeArray([
			...imports,
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

export const createLayerDependency = (dependencyName: string) => {
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

const createImport = (packageName: string, namedImport: string | undefined, ...namedBindings: (string | { value: string, as: string })[]): ts.ImportDeclaration => {
	const namedImports = [];
	for (const namedBinding of namedBindings) {
		if (typeof namedBinding == "string") {
			namedImports.push(factory.createImportSpecifier(
				false,
				undefined,
				factory.createIdentifier(namedBinding)
			))
		} else {
			namedImports.push(factory.createImportSpecifier(
				false,
				factory.createIdentifier(namedBinding.value),
				factory.createIdentifier(namedBinding.as)
			))
		}
	}

	const imports = factory.createImportDeclaration(
		undefined,
		factory.createImportClause(
			undefined,
			namedImport ? factory.createIdentifier(namedImport) : undefined,
			namedImports.length != 0 ? factory.createNamedImports(namedImports) : undefined
		),
		factory.createStringLiteral(packageName),
		undefined
	);
	return imports;
}

export function createRelativeImportPath(from: string, to: string): string {
	// a better way to detect node & workspace imports can be implemented
	if (!to.startsWith(".")) {
		return to
	}
	const fromPath = ts.sys.resolvePath(from);
	const toPath = ts.sys.resolvePath(to);
	// console.log(fromPath, "=>", toPath)

	const fromDir = posix.dirname(fromPath);
	let relativePath = posix.relative(fromDir, toPath);

	if (!relativePath.startsWith(".")) {
		relativePath = "./" + relativePath;
	}

	return relativePath;
}

export const createLayer = (layerName: string, dependencies: ts.VariableStatement[], body: ts.Statement[], ...other: ts.VariableStatement[]) => {
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