import { Effect, Layer } from "effect";
import { ContextWindow } from "recon";
import { LanguageModel } from "../languagemodel.ts";
import { connect } from "../knowledgebase.ts";
import { Behavior } from "./behavior.ts";

export const BehaviorTree = Layer.effect(Behavior, Effect.gen(function* () {
    const context = yield* ContextWindow;
    const kb = yield* connect("test.db");
    const languagemodel = yield* LanguageModel;
    const proto: Behavior.Behavior = {
        status: "ready",
        onInitialize: () => {
            proto.status = "running";
        },
        update: () => "running",
        onTerminate: (status: Behavior.Status) => {
            if (status === proto.status) {
                proto.status = "success";
            }
        }
    }
    return proto;
}))

export const make = <T,U>(definition: T, agent:U) => {
    return {src: definition, impl: agent}
}