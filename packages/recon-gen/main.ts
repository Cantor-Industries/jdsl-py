import { getEscapedText } from "./src/utils.ts";
import ts, { Node, SourceFile } from "typescript";

import root, { Root } from "./src/root.ts";
import actionMap from "./src/action.ts";

export const definition = `const definition = {
    "type": "root",
    "child": {    
        "type": "action",
        "call": "TryThis"
        "args": ["Play", "Hard", 12, true],     
    }
}
`

export const agent = `const agent = {
    TryThis: (action: string, arg: string, age: number, save: boolean) => {
        console.log("Agent Trying This");
    }
}`

const definitionAST = ts.createSourceFile(
    "definition.ts",
    definition,
    ts.ScriptTarget.ESNext,
    true,
    ts.ScriptKind.TS
)

const agentAST = ts.createSourceFile(
    "agent.ts",
    agent,
    ts.ScriptTarget.ESNext,
    true,
    ts.ScriptKind.TS
)

let parentObject: Root;
let agentTree = new Map<string, Node>();

const agentVisitor = (node: Node): Map<string, Node> => {
    const agentTree: Map<string, Node> = new Map();
    for (const child of node.getChildAt(1).getChildren()) {
        if (ts.isPropertyAssignment(child)) {
            const key = child.getChildAt(0);
            const value = child.getChildAt(2);
            agentTree.set(key.getText(), value);
        }
    }
    return agentTree;
}

const buildRoot = () => {
    parentObject = root;
    root.addImport("effect", "Effect", "Context", "Layer");
    root.addContext();
    root.addLayer();
}

const buildAction = (tree: Map<string, Node>, parent: Root) => {
    const actionName = tree.get("call");
    if (!actionName) {
        console.error("Action must have a call attribute");
        return
    }
    actionMap.addAction(getEscapedText(actionName) + "Action");
    actionMap.addImport("effect", "Context", "Data", "Effect", "Layer");
    actionMap.addContext();
    actionMap.addLayer();
    parent.addChild(getEscapedText(actionName) + "Action");

    
}

const visitTree = (node: Node, parent: Root): Node | undefined => {
    const tree: Map<string, Node> = new Map();
    for (const child of node.getChildAt(1).getChildren()) {
        if (ts.isPropertyAssignment(child)) {
            const key = child.getChildAt(0);
            const value = child.getChildAt(2);
            tree.set(getEscapedText(key), value);
        }
    }
    for (const [key, value] of tree) {
        if (key == "type") {
            const valueName = getEscapedText(value);
            if (valueName == "root") {
                const child = tree.get("child");
                if (child == undefined) {
                    console.error("Root Node Must Have child property");
                    break;
                }
                buildRoot();
                return visitTree(child, root);
            } else if (valueName === "action") {
                buildAction(tree, parent);
            }
        }
    }
    return node;
}

const agentWalker = (node: Node): Node | undefined => {
    if (ts.isObjectLiteralExpression(node)) {
        agentTree = agentVisitor(node);
        return node;
    } else {
        return node.forEachChild(agentWalker);
    }
}

const definitionWalker = (node: Node): Node | undefined => {
    if (ts.isObjectLiteralExpression(node)) {
        return visitTree(node, root);
    } else {
        return node.forEachChild(definitionWalker)
    }
}

const transformer = (sourceFile: SourceFile, visitor: (node: Node)=> Node | undefined) => {
    ts.visitNode(sourceFile, visitor, undefined);
}

transformer(agentAST, agentWalker);
transformer(definitionAST, definitionWalker);

root.print();
console.log("");
actionMap.print();
console.log("");
for (const [key, value] of agentTree) {
    console.log(key, "->", value.getText());
}