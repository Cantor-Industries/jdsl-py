import { Context, Effect, Either, Layer } from "effect";
import { BlockLimit, BlockLimitExceededError, CharacterLimit } from "./limit.ts";

export class MemBlock extends Context.Tag("Memblock")<MemBlock, MemBlock.MemBlock>() { }

export declare namespace MemBlock {
    export interface Block {
        readonly label: string;
        value: string;
        readonly limit: number;
        readonly description?: string;
    }
    export interface MemBlock {
        make: (label: string, limit: number, decription?: string) => Effect.Effect<Block, never, never>;
        update: (block: MemBlock.Block, value: string) => Effect.Effect<void, BlockLimitExceededError, never>
    }
}

export const CharMemBlock = Layer.effect(MemBlock, Effect.gen(function* () {
    const checker = yield* BlockLimit;
    const proto = {
        make: (label: string, limit: number, decription?: string) => Effect.sync(() => {
            const block: MemBlock.Block = {
                label: label,
                value: " ",
                limit: limit,
                description: decription,
            }
            return block;
        }),
        update: (block: MemBlock.Block, value: string) => Effect.gen(function* (){
            yield* checker.check(value, block.limit);
            block.value = value;
        })
    }
    return proto;
}))

const program = Effect.gen(function* () {
    const memBlock = yield* MemBlock;
    const block = yield* memBlock.make("start", 4, "now");
    yield* memBlock.update(block, "Luiz you are lazy today");
    console.log(block);
})

const programLive = Effect.provide(program, CharMemBlock);
const runMain = Effect.provide(programLive, CharacterLimit);

const final = Effect.gen(function* () {
    const failureOrSuccess = yield* Effect.either(runMain);
    if (Either.isLeft(failureOrSuccess)) {
        const error = failureOrSuccess.left;
        console.log(`Error occured due to ${error._tag}`);
    } else {
        return failureOrSuccess.right;
    }
})
Effect.runSync(final);