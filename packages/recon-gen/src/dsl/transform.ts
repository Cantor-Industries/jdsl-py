import ts, { factory, type Node, type SourceFile } from "typescript";
import { getEscapedText } from "./node.ts";
import { Root, RootBuilder } from "./root.ts";
import { Action, ActionBuilder } from "./action.ts";
import { Effect } from "effect";
import { ReconLanguageServer } from "../lsp/lsp.ts";
import { normalize, VFS } from "../lsp/vfs.ts";
import { Sequence, SequenceBuilder } from "./sequence.ts";
import { Selector, SelectorBuilder } from "./selector.ts";
import { ReconResolver } from "../lsp/resolver.ts";
import { ReconRunner } from "./runner.ts";
import { ContextBuilder } from "./context.ts";

export class Tools extends Effect.Service<Tools>()(
    "Tools",
    {
        accessors: true,
        effect: Effect.sync(() => {
            const tools = new Map<string, ts.ArrowFunction>();
            const toolVisitor = (node: Node) => {
                for (const child of node.getChildAt(1).getChildren()) {
                    if (ts.isPropertyAssignment(child)) {
                        const key = child.name;
                        const value = child.initializer;
                        if (ts.isArrowFunction(value)) {
                            const arrowFunction = factory.updateArrowFunction(
                                value,
                                value.modifiers,
                                value.typeParameters,
                                value.parameters,
                                undefined,
                                factory.createToken(ts.SyntaxKind.EqualsGreaterThanToken),
                                value.body
                            )
                            tools.set(key.getText(), arrowFunction);
                        } else if (ts.isFunctionExpression(value)) {
                            const arrowFunction = factory.createArrowFunction(
                                value.modifiers,
                                value.typeParameters,
                                value.parameters,
                                undefined,
                                factory.createToken(ts.SyntaxKind.EqualsGreaterThanToken),
                                value.body ?? factory.createBlock([], true)
                            );
                            tools.set(key.getText(), arrowFunction);
                        } else if (ts.isPropertyAccessExpression(value)) {
                            throw new Error(`Property Access Expressions not yet supported in Recon`);
                        } else {
                            throw new Error(`No arrow function declared in property: ${value.getText()}, ${value.kind}`);
                        }
                    }
                }
            };
            const toolWalker = (node: Node): Node => {
                if (ts.isObjectLiteralExpression(node)) {
                    toolVisitor(node);
                    return node;
                } else {
                    return node.forEachChild(toolWalker)!;
                }
            }
            const init = (nodes: Node[]) => {
                nodes.forEach(node => toolWalker(node));
                return tools;
            }
            return { init, tools } as const;
        })
    }
) { }

export class Skills extends Effect.Service<Skills>()(
    "Skills",
    {
        effect: Effect.gen(function* () {
            const rootBuilder = yield* RootBuilder;
            const actionBuilder = yield* ActionBuilder;
            const sequenceBuilder = yield* SequenceBuilder;
            const selectorBuilder = yield* SelectorBuilder;
            const contextBuilder = yield* ContextBuilder;
            const reconRunner = yield* ReconRunner;
            let runnerInitialized = false;

            const skillVisitor = (node: Node): Action | Root | Sequence | Selector => {
                const skill: Map<string, Node> = new Map();
                node.forEachChild(child => {
                    if (ts.isPropertyAssignment(child)) {
                        const key = child.name;
                        const value = child.initializer;
                        skill.set(getEscapedText(key), value);
                    }
                })
                for (const [key, value] of skill) {
                    if (key == "type") {
                        const valueName = getEscapedText(value);
                        if (valueName == "root") {
                            const childNode = skill.get("child");
                            if (childNode == undefined) {
                                console.error("Root Node Must Have Child Property");
                                break;
                            }
                            console.log("Starting to explore", rootBuilder.root.name);
                            if (skill.get("name")) {
                                const name = getEscapedText(skill.get("name")!);
                                rootBuilder.buildRoot(name);
                            } else {
                                rootBuilder.buildRoot();
                            }
                            const child = skillVisitor(childNode);

                            const context = skill.get("context");
                            if (context) {
                                const importStatement = contextBuilder.createImport();
                                rootBuilder.addImport(importStatement.moduleSpecifier, importStatement.importClause);
                                rootBuilder.addPluginDependency("ContextWindow");
                                if (!contextBuilder.isInitialized) {
                                    reconRunner.addImport(importStatement.moduleSpecifier, importStatement.importClause);
                                    reconRunner.addServiceDependency("ContextWindow");
                                }
                                if (ts.isObjectLiteralExpression(context)) {
                                    const body = contextBuilder.createBody(context);
                                    rootBuilder.addPluginBody(body);
                                }
                            }

                            if (child instanceof Root) {
                                return rootBuilder.root();
                            }
                            rootBuilder.addChild(child);
                            if (runnerInitialized) {
                                reconRunner.addChild(rootBuilder.root());
                            } else {
                                reconRunner.buildRunner();
                                reconRunner.addChild(rootBuilder.root());
                                runnerInitialized = true;
                            }
                            console.log("Finished exploring Root");
                            return rootBuilder.root();
                        }
                        else if (valueName === "selector") {
                            const childNodes = skill.get("children");
                            if (childNodes == undefined) {
                                throw new Error("Selector Node Must Have Children Property");
                            }
                            selectorBuilder.buildSelector();
                            const selector = selectorBuilder.selector();
                            console.log("Starting to explore", selector.name);

                            const context = skill.get("context");
                            if (context) {
                                const importStatement = contextBuilder.createImport();
                                selector.addImport(importStatement.moduleSpecifier, importStatement.importClause);
                                selector.addPluginDependency("ContextWindow");
                                if (!contextBuilder.isInitialized) {
                                    reconRunner.addImport(importStatement.moduleSpecifier, importStatement.importClause);
                                    reconRunner.addServiceDependency("ContextWindow");
                                }
                                if (ts.isObjectLiteralExpression(context)) {
                                    const body = contextBuilder.createBody(context);
                                    selector.addPluginBody(body);
                                }
                            }

                            childNodes.forEachChild(childNode => {
                                const child = skillVisitor(childNode);
                                if (!(child instanceof Root)) {
                                    selectorBuilder.addChild(selector, child);
                                }

                            })
                            console.log("Finished exploring", selector.name);
                            return selector;
                        }
                        else if (valueName === "sequence") {
                            const childNodes = skill.get("children");
                            if (childNodes == undefined) {
                                throw new Error("Sequence Node Must Have Children Property");
                            }
                            sequenceBuilder.buildSequence();
                            const sequence = sequenceBuilder.sequence();
                            console.log("Starting to explore", sequence.name);

                            const context = skill.get("context");
                            if (context) {
                                const importStatement = contextBuilder.createImport();
                                sequence.addImport(importStatement.moduleSpecifier, importStatement.importClause);
                                sequence.addPluginDependency("ContextWindow");
                                if (!contextBuilder.isInitialized) {
                                    reconRunner.addImport(importStatement.moduleSpecifier, importStatement.importClause);
                                    reconRunner.addServiceDependency("ContextWindow");
                                }
                                if (ts.isObjectLiteralExpression(context)) {
                                    const body = contextBuilder.createBody(context);
                                    sequence.addPluginBody(body);
                                }
                            }

                            childNodes.forEachChild(childNode => {
                                const child = skillVisitor(childNode);
                                if (!(child instanceof Root)) {
                                    sequenceBuilder.addChild(sequence, child);
                                }
                            })
                            console.log("Finished exploring", sequence.name);
                            return sequence;
                        }
                        else if (valueName === "action") {
                            actionBuilder.buildAction(skill);
                            console.log("Starting to explore", actionBuilder.action().name);

                            const context = skill.get("context");
                            if (context) {
                                const importStatement = contextBuilder.createImport();
                                actionBuilder.addImport(importStatement.moduleSpecifier, importStatement.importClause);
                                actionBuilder.addPluginDependency("ContextWindow");
                                if (!contextBuilder.isInitialized) {
                                    reconRunner.addImport(importStatement.moduleSpecifier, importStatement.importClause);
                                    reconRunner.addServiceDependency("ContextWindow");
                                }
                                if (ts.isObjectLiteralExpression(context)) {
                                    const body = contextBuilder.createBody(context);
                                    actionBuilder.addPluginBody(body);
                                }
                            }

                            console.log("Finished exploring", actionBuilder.action().name);
                            return actionBuilder.action();
                        }

                    }
                }
                return rootBuilder.root();
            }

            const skillWalker = (node: Node): Node => {
                if (ts.isObjectLiteralExpression(node)) {
                    skillVisitor(node)!;
                    return node;
                } else {
                    return node.forEachChild(skillWalker)!
                }
            }
            const init = (nodes: Node[]) => {
                nodes.forEach(node => skillWalker(node));
            }
            return { init } as const;
        }),
        dependencies: [ActionBuilder.Default, RootBuilder.Default, SequenceBuilder.Default, SelectorBuilder.Default, ReconRunner.Default, ContextBuilder.Default]
    }
) { }

export class Transform extends Effect.Service<Transform>()(
    "Transform",
    {
        effect: Effect.gen(function* () {
            const tools = yield* Tools;
            const skills = yield* Skills;
            const languageService = yield* ReconLanguageServer;
            const resolver = yield* ReconResolver;
            const vfs = yield* VFS;

            const transform = (sourceFile: SourceFile) => Effect.sync(() => {
                const { toolsNodes, skillsNodes } = resolver.resolve(sourceFile)

                console.log(`Discovered ${toolsNodes.length} Tool definition(s)`);
                tools.init(toolsNodes);
                console.log(`Discovered ${skillsNodes.length} Skill definition(s)`);
                skills.init(skillsNodes);
                const ignoredCodes = new Set([
                    5097, // allow .ts extension imports
                    6133, // declared but never used
                    6196, // declared but never read
                ]);
                vfs.writeFiles();

                let diagnostics: ts.Diagnostic[] = []
                vfs.fileNames().forEach(file => {
                    const diags = languageService
                        .getSemanticDiagnostics(normalize(file))
                        .filter(diagnostic => !ignoredCodes.has(diagnostic.code));
                    diagnostics = diagnostics.concat(diags)
                })
                if (diagnostics.length) {
                    throw new Error(
                        ts.formatDiagnosticsWithColorAndContext(diagnostics, {
                            getCanonicalFileName: f => f,
                            getCurrentDirectory: () => "/",
                            getNewLine: () => "\n"
                        })
                    );
                }
                vfs.writeFiles();
            });
            return { transform } as const;
        }),
        dependencies: [Skills.Default, ReconResolver.Default]
    }
) { }