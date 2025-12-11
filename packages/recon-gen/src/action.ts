import { NodeCreator } from "./utils.ts";
import ts, {Node, factory } from "typescript";

export class Action extends NodeCreator {
    // deno-lint-ignore no-explicit-any
    private args: any[];
    // deno-lint-ignore no-explicit-any
    private runBody: any[];

    constructor (name: string) {
        super(name);
        this.args = [];
        this.runBody = [];
    }
    
    // deno-lint-ignore no-explicit-any
    addArgs (...args: any[]) {
        this.args = args
    }

    override addLayerBody(): void {
      
    }
};
export class ActionMap {
    private lastAction: string
    private actions: Map<string, Action>

    constructor () {
        this.actions = new Map<string, Action>();
        this.lastAction = "";
    }

    addArgs (...args: any[]) {
        this.actions.get(this.lastAction)?.addArgs(args);
    }

    addAction (name: string) {
        this.lastAction = name;
        this.actions.set(name, new Action(name));
    }

    addImport(packageName: string, ...values: string[]) {
        this.actions.get(this.lastAction)?.addImport(packageName, ...values)
    }

    addContext() {
        this.actions.get(this.lastAction)?.addContext();
        this.actions.get(this.lastAction)?.addError();
    }

    addLayer() {
        this.actions.get(this.lastAction)?.addLayer()
    }

    print() {
        for (const action of this.actions) {
            action[1].print()
        }
    }
}

const createActonLayerBody = () => {

}

const actions = new ActionMap();

export default actions;