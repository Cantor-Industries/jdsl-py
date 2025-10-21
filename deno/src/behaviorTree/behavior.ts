import { Context } from "effect";

const BehaviorTag = Context.Tag("Behavior")<Behavior, Behavior.Behavior>();
export class Behavior extends BehaviorTag {};

export declare namespace Behavior {
    export type Status = "ready" |  "running" | "success" | "failed";
    export interface Behavior {
        status: Status;
        onInitialize: () => void;
        update: () => Status;
        onTerminate: (status: Status) => void
    }
}
