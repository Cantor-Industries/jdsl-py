import { getEscapedText } from "./src/utils.ts";
import ts, { factory, Node, SourceFile } from "typescript";

import root, { Root } from "./src/root.ts";
import actionMap, { ActionMap } from "./src/action.ts";

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
const agentObject = new Map<string, Node>();

const transformAgent = (sourceFile: SourceFile) => {
    ts.visitNode(sourceFile, agentVisitor, undefined);
}


const parseArgs = (args: Node, actionMap: ActionMap) => {
    args;
}
const agentVisitor = (node: Node): Node | undefined => {
    let key: Node | undefined;
    let value: Node | undefined;
    let args: Node | undefined;
    let block: Node | undefined;
    if (ts.isPropertyAssignment(node)) {
        key = node.getChildAt(0);
        value = node.getChildAt(2);
        const text = key.getText();
        agentObject.set(text, value)
        // console.log(key.getText(),":",value.getText(),"\n");
    }
    if (ts.isArrowFunction(node)) {
        block = node.getChildAt(4);
        args = node.getChildAt(1);
        // console.log(block.getText(), "\n");
        console.log(args.getText());
    }
    return node.forEachChild(agentVisitor);
}
const parseType = (value: string) => {
    switch (value) {
        case "root":
            root.addImport("effect", "Effect", "Context", "Layer");
            root.addContext();
            root.addLayer();
            parentObject = root;
            break;
        case "action":

            break;
        default:
            break;
    }
}

const definitionVisitor = (node: Node): Node | undefined => {
    if (ts.isPropertyAssignment(node)) {
        const key = node.getChildAt(0);
        const value = node.getChildAt(2);
        switch (getEscapedText(key)) {
            case "type":
                parseType(getEscapedText(value))
                break;
            case "child":
                break;
            case "children":
                break;
            case "call":
                actionMap.addAction(getEscapedText(value) + "Action");
                actionMap.addImport("effect", "Context", "Data", "Effect", "Layer");
                actionMap.addContext();
                actionMap.addLayer();
                parentObject.addChild(getEscapedText(value) + "Action");
                break;
            case "args":
                parseArgs(node, actionMap);
                console.log("Args:", node.getChildAt(2).getFullText())
                actionMap.addArgs(node.getChildAt(2))
                break;
        }
    }
    return node.forEachChild(definitionVisitor);
}

const transformer = (sourceFile: SourceFile) => {
    ts.visitNode(sourceFile, definitionVisitor, undefined);
}

transformAgent(agentAST);
// console.log(agentObject)
transformer(definitionAST);

// root.print();
// console.log("");
actionMap.print();