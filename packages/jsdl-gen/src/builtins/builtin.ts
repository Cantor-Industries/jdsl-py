import { Effect } from "effect";

export class BuiltinBuilder extends Effect.Service<BuiltinBuilder>()(
    "BuiltinBuilder",
    {
        effect: Effect.gen(function* () {

            const builtins = ["generateText", "streamText"];

            const has = (callName: string) => {
                if (builtins.includes(callName)) {
                    return true;
                } else {
                    return false;
                }
            }

            const getRunFunction = (callName: string) => {

            }
            return { has, getRunFunction } as const;
        })
    }
){}