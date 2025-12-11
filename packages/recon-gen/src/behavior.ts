import { Context, Effect } from "effect";

const BehaviorTag = Context.Tag("Behavior")<Behavior, Behavior.Behavior>();
export class Behavior extends BehaviorTag { };

const definition = {
    "type": "root",
    "child": {
        "type": "selector",
        "children": [
            {
                "type": "action",
                "call": "TryThis"
            },
            {
                "type": "action",
                "call": "ThenTryThis"
            },
            {
                "type": "action",
                "call": "TryThisLast"
            }
        ]
    }
}

const definition2 = {
    "type": "root",
    "child": {
        "type": "selector",
        "children": [
            {
                "type": "sequence",
                "children": [
                    [
                        {
                            "type": "action",
                            "call": "TryThis"
                        },
                        {
                            "type": "action",
                            "call": "ThenTryThis"
                        },
                        {
                            "type": "action",
                            "call": "TryThisLast"
                        }
                    ]
                ]
            },
            {
                "type": "sequence",
                "children": [
                    [
                        {
                            "type": "action",
                            "call": "TryThis"
                        },
                        {
                            "type": "action",
                            "call": "ThenTryThis"
                        },
                        {
                            "type": "action",
                            "call": "TryThisLast"
                        }
                    ]
                ]
            }
        ]
    }
}

export declare namespace Behavior {
    export enum Status {
        READY="ready",
        RUNNING="running",
        SUCCESS="success",
        FAILED="failed"
    }
    export interface Behavior {
        status: Status;
        // result: T;
        // children: Behavior[];
        update: () => Effect.Effect<Status, never, never>;
    }
}