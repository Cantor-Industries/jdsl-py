import { Context, Data, Effect, Layer } from "effect";

const BlockLimitTag: Context.TagClass<BlockLimit, "BlockLimit", BlockLimit.Limiter> = Context.Tag("BlockLimit")<BlockLimit, BlockLimit.Limiter>(); 
export class BlockLimit extends BlockLimitTag{ };

// deno-lint-ignore ban-types
const BlockLimitExceededErrorTag = Data.TaggedError("BlockLimitExceededError")<{}> ;
export class BlockLimitExceededError extends BlockLimitExceededErrorTag{ }

export declare namespace BlockLimit {
    export interface Limiter {
        check: (value: string, limit: number) => Effect.Effect<void, BlockLimitExceededError, never>;
    }
}

export const CharacterLimit: Layer.Layer<BlockLimit, never, never> = Layer.effect(BlockLimit, Effect.sync(() => {
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

export const TokenLimit: Layer.Layer<BlockLimit, never, never> = Layer.effect(BlockLimit, Effect.sync(() => {
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

export const WordLimit: Layer.Layer<BlockLimit, never, never> = Layer.effect(BlockLimit, Effect.sync(() => {
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