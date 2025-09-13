import { Context, Effect, Layer } from "effect";
import { ulid, type ULID } from "ulid";
import { BlockLimit, type BlockLimitExceededError,} from "./limit.ts";

const MemBlockTag = Context.Tag("Memblock")<MemBlock, MemBlock.MemBlock>();
export class MemBlock extends MemBlockTag { };

export declare namespace MemBlock {
    export interface Block {
        readonly id: ULID;
        readonly label: string;
        value: string;
        readonly limit: number;
        readonly description?: string;
        readonly relationships?: Relationship[];
    }
    export interface Relationship {
        [type: string]: ULID;
    }
    export interface MemBlock {
        load: (id: string) => Effect.Effect<void, never, never>;
        make: (label: string, limit: number, decription?: string) => Effect.Effect<Block, never, never>;
        update: (block: MemBlock.Block, value: string) => Effect.Effect<void, BlockLimitExceededError, never>
    }
}

export const CharMemBlock: Layer.Layer<MemBlock, never, BlockLimit> = Layer.effect(MemBlock, Effect.gen(function* () {
    const checker = yield* BlockLimit;
    const proto = {
        load: (id: string) => Effect.sync (() => {
            id;
        }),
        make: (label: string, limit: number, decription?: string) => Effect.sync(() => {
            const block: MemBlock.Block = {
                id: ulid(),
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
