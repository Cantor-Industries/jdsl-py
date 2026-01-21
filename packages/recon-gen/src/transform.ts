import ts, { Node, SourceFile } from "typescript";
import { getEscapedText } from "./node.ts";
import { Root, RootBuilder } from "./root.ts";
import { Action, ActionBuilder } from "./action.ts";
import { Effect } from "effect";
import { ReconLanguageServer } from "./lsp.ts";
import { normalize, VFS } from "./vfs.ts";
import { Sequence, SequenceBuilder } from "./sequence.ts";

export class Tools extends Effect.Service<Tools>()(
    "Tools",
    {
        accessors: true,
        effect: Effect.sync(() => {
            const tools = new Map<string, ts.ArrowFunction>();
            console.log("TOOLS INIT");
            const toolVisitor = (node: Node) => {
                for (const child of node.getChildAt(1).getChildren()) {
                    if (ts.isPropertyAssignment(child)) {
                        const key = child.getChildAt(0);
                        const value = child.getChildAt(2);
                        if (ts.isArrowFunction(value)) {
                            tools.set(key.getText(), value);
                        } else {
                            throw new Error("No arrow function declared in property");
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
            const proto = {
                init: (nodes: Node[]) => {
                    nodes.forEach(node => toolWalker(node));
                    console.log("Tools: ", [...tools.keys()])
                    return tools;
                },
                tools: tools
            };
            return proto;
        })
    }
) { }

export class Skills extends Effect.Service<Skills>()(
    "Skills",
    {
        effect: Effect.gen(function* () {
            console.log("SKILLS INIT");
            const rootBuilder = yield* RootBuilder;
            const actionBuilder = yield* ActionBuilder;
            const sequenceBuilder = yield* SequenceBuilder;
            // const vfs = yield* VFS;


            const skillVisitor = (node: Node): Action | Root | Sequence => {
                const skill: Map<string, Node> = new Map();
                for (const child of node.getChildAt(1).getChildren()) {
                    if (ts.isPropertyAssignment(child)) {
                        const key = child.getChildAt(0);
                        const value = child.getChildAt(2);
                        skill.set(getEscapedText(key), value);
                    }
                }

                for (const [key, value] of skill) {
                    if (key == "type") {
                        const valueName = getEscapedText(value);
                        if (valueName == "root") {
                            const childNode = skill.get("child");
                            if (childNode == undefined) {
                                console.error("Root Node Must Have Child Property");
                                break;
                            }
                            if (skill.get("name")) {
                                const name = getEscapedText(skill.get("name")!);
                                rootBuilder.buildRoot(name);
                            } else {
                                rootBuilder.buildRoot();
                            }
                            const child = skillVisitor(childNode);
                            if (child instanceof Root) {
                                return rootBuilder.root;
                            }
                            rootBuilder.addChild(child);
                            console.log("Finished exploring Root");
                            return rootBuilder.root;
                        }
                        else if (valueName === "sequence") {
                            const childNodes = skill.get("children");
                            if (childNodes == undefined) {
                                throw new Error("Sequence Node Must Have Children Property");
                            }
                            sequenceBuilder.buildSequence();
                            console.log("Starting to explore", sequenceBuilder.sequence().name);
                            childNodes.forEachChild(childNode => {
                                const child = skillVisitor(childNode);
                                if (child instanceof Sequence) {
                                    sequenceBuilder.pop();
                                    sequenceBuilder.addChild(child);
                                } else if (!(child instanceof Root)) {
                                    sequenceBuilder.addChild(child);
                                }

                            })
                            console.log("Finished exploring", sequenceBuilder.sequence().name);

                            return sequenceBuilder.sequence();
                        }
                        else if (valueName === "action") {
                            actionBuilder.buildAction(skill);
                            console.log("Finished exploring", actionBuilder.action().name)
                            return actionBuilder.action();
                        }

                    }
                }
                return rootBuilder.root;
            }

            const skillWalker = (node: Node): Node => {
                if (ts.isObjectLiteralExpression(node)) {
                    skillVisitor(node)!;
                    return node;
                } else {
                    return node.forEachChild(skillWalker)!
                }
            }
            const proto = {
                init: (nodes: Node[]) => {
                    nodes.forEach(node => skillWalker(node));
                },
            };
            return proto;
        }),
        dependencies: [ActionBuilder.Default, RootBuilder.Default, SequenceBuilder.Default]
    }
) { }

export class Transform extends Effect.Service<Transform>()(
    "Transform",
    {
        effect: Effect.gen(function* () {
            console.log("TRANSFORM INIT");
            const tools = yield* Tools;
            const skills = yield* Skills;
            const languageService = yield* ReconLanguageServer;
            const vfs = yield* VFS;

            const transform = (sourceFile: SourceFile) => Effect.sync(() => {
                const toolsNodes: Node[] = [];
                const skillsNodes: Node[] = [];

                const visitor = (node: Node): Node => {
                    if (ts.isSatisfiesExpression(node)) {
                        const satisfiesType = node.getChildAt(2);
                        if (satisfiesType.getText().startsWith("Tool")) {
                            toolsNodes.push(node.getChildAt(0));
                        } else if (satisfiesType.getText().startsWith("Skill")) {
                            skillsNodes.push(node.getChildAt(0));
                        }
                    }

                    return node.forEachChild(visitor)!
                }
                ts.visitNode(sourceFile, visitor, undefined);

                console.log("Initializing tools");
                tools.init(toolsNodes);
                console.log("Initializing skills");
                skills.init(skillsNodes);
                vfs.writeFiles();

                const diagnostics = languageService
                    .getSemanticDiagnostics(normalize("./dist/Root.ts"))
                    .filter(diagnostic => {
                        if (diagnostic.code != 5097) return diagnostic
                    });
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
            return transform
        }),
        dependencies: [Skills.Default]
    }
) { }