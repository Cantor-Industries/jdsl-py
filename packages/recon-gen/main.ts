import { getEscapedText } from "./src/utils.ts";
import ts, { Node, SourceFile } from "typescript";

import root, { Root } from "./src/root.ts";
import { ActionMap } from "./src/action.ts";

export const definition = `const definition = {
    "type": "root",
    "child": {    
        "type": "action",
        "call": "TryThis"
        "args": ["Play", "Hard", 12, {buffer: true, length: 2048}, console.log("Hello")] 
    }
}
`

export const agent = `const agent = {
    TryThis: (action: string, arg: string, age: number, obj: {hello: string}, save: boolean) => {
        console.log("Agent Trying This");
        return action;
    },
    ThenTryThis: (action: string, arg: string, age: number, save: boolean) => {
        console.log("Agent Trying This");
        return action;
    },
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

let agentTree = new Map<string, ts.ArrowFunction>();

const agentVisitor = (node: Node) => {
    const agentTree: Map<string, ts.ArrowFunction> = new Map();
    for (const child of node.getChildAt(1).getChildren()) {
        if (ts.isPropertyAssignment(child)) {
            const key = child.getChildAt(0);
            const value = child.getChildAt(2);
            agentTree.set(key.getText(), value as ts.ArrowFunction);
        }
    }
    return agentTree;
}

const buildRoot = () => {
    root.addImport("effect", "Context", "Data", "Effect", "Either", "Layer");
    root.addError();
    root.addContext();
    root.addLayer();
}

const buildAction = (tree: Map<string, Node>, parent: Root) => {
    const actionName = tree.get("call");
    if (!actionName) {
        console.error("Action must have a call attribute");
        return
    }
    actionMap.addAction(getEscapedText(actionName) + "Action", "/virtual/src/actions/");
    actionMap.addImport("effect", "Context", "Data", "Effect", "Layer");
    actionMap.addContext();

    const args = tree.get("args");
    if (args && ts.isArrayLiteralExpression(args)) {
        actionMap.addArgs(args)
    }
    actionMap.addLayer();
    parent.addChild(actionMap.action());


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
            }
            else if (valueName === "action") {
                buildAction(tree, parent);
            }
        }
    }
    return node;
}

const agentWalker = (node: Node): Node => {
    if (ts.isObjectLiteralExpression(node)) {
        agentTree = agentVisitor(node);
        return node;
    } else {
        return node.forEachChild(agentWalker)!;
    }
}

const definitionWalker = (node: Node): Node=> {
    if (ts.isObjectLiteralExpression(node)) {
        return visitTree(node, root)!;
    } else {
        return node.forEachChild(definitionWalker)!
    }
}

const transformer = (sourceFile: SourceFile, visitor: (node: Node) => Node) => {
    ts.visitNode(sourceFile, visitor, undefined);
}

transformer(agentAST, agentWalker);
const actionMap = new ActionMap(agentTree);
transformer(definitionAST, definitionWalker);

// console.log("");
// root.print();
// console.log("");
actionMap.print();
// console.log("");
// for (const [key, value] of agentTree) {
//     console.log(key, "->", value.getText());
// }