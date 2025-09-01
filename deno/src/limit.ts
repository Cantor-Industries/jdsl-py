import { Context, Data, Effect, Layer } from "effect";

export class BlockLimit extends Context.Tag("BlockLimit")<BlockLimit, BlockLimit.Limiter>() { }

// deno-lint-ignore ban-types
export class BlockLimitExceededError extends Data.TaggedError("BlockLimitExceededError")<{}> { }

export declare namespace BlockLimit {
    export interface Limiter {
        check: (value: string, limit: number) => Effect.Effect<void, BlockLimitExceededError, never>;
    }
}

export const CharacterLimit = Layer.effect(BlockLimit, Effect.sync(() => {
    const proto = {
        check: (value: string, limit: number) => Effect.try({
            try: () => {
                if (value.length > limit) throw new BlockLimitExceededError();
            },
            catch: () => new BlockLimitExceededError()
        }),
    }
    return proto;
}))

export const TokenLimit = Layer.effect(BlockLimit, Effect.sync(() => {
    const proto = {
        check: (value: string, limit: number) => Effect.try({
            try: () => {
                const words = value.split(/\s+/); // split by any whitespace character
                if (words.length > limit) throw new BlockLimitExceededError();
            },
            catch: () => new BlockLimitExceededError()
        }),
    }
    return proto;
}))

export const WordLimit = Layer.effect(BlockLimit, Effect.sync(() => {
    const proto = {
        check: (value: string, limit: number) => Effect.try({
            try: () => {
                const words = value.split(/\s+/); // split by any whitespace character
                if (words.length > limit) throw new BlockLimitExceededError();
            },
            catch: () => new BlockLimitExceededError()
        }),
    }
    return proto;
}))