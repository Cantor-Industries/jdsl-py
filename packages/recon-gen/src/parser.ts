import ts, { Node, SourceFile } from "typescript";
import { createRelativeImportPath ,getEscapedText } from "./utils.ts";
import root, { Root } from "./root.ts";
import { ActionMap } from "./action.ts";
import { Effect } from "effect";
import { normalize, VirtualFS } from "./vfs.ts";

export const tools = new Map<string, ts.ArrowFunction>();
export const actionMap = new ActionMap(tools);

export const buildRoot = () => {
    root.addImport("effect", "Context", "Data", "Effect", "Either", "Layer");
    root.addImport(createRelativeImportPath(root.path(), "./dist/src/types.ts"), "Status")
    root.addError();
    root.addContext();
    root.addLayer();
}

export const buildAction = (actionMap: ActionMap, skill: Map<string, Node>, parent: Root) => {
    const actionName = skill.get("call");
    if (!actionName) {
        console.error("Action must have a call attribute");
        return
    }
    actionMap.addAction(getEscapedText(actionName) + "Action", "./dist/src/actions/");
    actionMap.addImport("effect", "Context", "Data", "Effect", "Layer");
    actionMap.addImport(createRelativeImportPath(actionMap.path(), "./dist/src/types.ts"), "Status");
    actionMap.addContext();

    const args = skill.get("args");
    if (args && ts.isArrayLiteralExpression(args)) {
        actionMap.addArgs(args)
    }
    actionMap.addLayer();
    parent.addChild(actionMap.action());
}

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
}

export const toolWalker = (node: Node): Node => {
    if (ts.isObjectLiteralExpression(node)) {
        toolVisitor(node);
        return node;
    } else {
        return node.forEachChild(toolWalker)!;
    }
}

const skillVisitor = (node: Node, parent: Root): Node | undefined => {
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
                const child = skill.get("child");
                if (child == undefined) {
                    console.error("Root Node Must Have child property");
                    break;
                }
                buildRoot();
                return skillVisitor(child, root);
            }
            else if (valueName === "action") {
                buildAction(actionMap, skill, parent);
            }
        }
    }
    return node;
}

export const skillWalker = (node: Node): Node => {
    if (ts.isObjectLiteralExpression(node)) {
        return skillVisitor(node, root)!;
    } else {
        return node.forEachChild(skillWalker)!
    }
}

export const transformer = (sourceFile: SourceFile, visitor: (node: Node) => Node) => {
    ts.visitNode(sourceFile, visitor, undefined);
}

// deno-lint-ignore require-yield
export const transform = (sourceFile: SourceFile) => Effect.gen(function* () {
    const visitor = (node: Node): Node => {
        if (ts.isSatisfiesExpression(node)) {
            const satisfiesType = node.getChildAt(2);
            if (satisfiesType.getText().startsWith("Tool")) {
                toolWalker(node.getChildAt(0));
            } else if (satisfiesType.getText().startsWith("Skill")) {
                skillWalker(node.getChildAt(0));
            }
        }

        return node.forEachChild(visitor)!
    }
    ts.visitNode(sourceFile, visitor, undefined);

    const vfs = new VirtualFS();
    vfs.set(normalize('dist/src/types.ts'), `
        export enum Status {
            READY = "ready",
            RUNNING = "running",
            SUCCESS = "success",
            FAILED = "failed"
        }
    `)
    vfs.set(root.path(), root.print());
    for (const [_, action] of actionMap.getActions()) {
        vfs.set(action.path(), action.print());
    }
    console.log(vfs.fileNames());
    return vfs;
})