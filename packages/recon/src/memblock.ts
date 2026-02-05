import { Context, Effect, Layer } from "effect";
import { ulid, type ULID } from "ulid";
import { 
    BlockLimit, 
    CharacterLimit, 
    TokenLimit, 
    WordLimit, 
    type BlockLimitExceededError
} from "recon/limit";
import { Db } from "@floq/kv";

const MemBlockTag = Context.Tag("Memblock")<MemBlock, MemBlock.MemBlock>();
export class MemBlock extends MemBlockTag { };

export declare namespace MemBlock {
    export interface Block {
        readonly id: ULID;
        readonly label: string;
        value: string;
        readonly limit: number;
        readonly description?: string;
        tags?: string[];
        readonly relationships?: Relationship[];
    }
    export interface Relationship {
        [type: string]: ULID;
    }
    export interface MemBlock {
        load: (id: Db.Key) => Effect.Effect<void, never, never>;
        // make: (label: string, limit: number, decription?: string) => Effect.Effect<Block, BlockLimitExceededError, never>;
        // update: (block: MemBlock.Block, value: string) => Effect.Effect<void, BlockLimitExceededError, never>
    }
}

const MemBlockLive: Layer.Layer<MemBlock, never, BlockLimit> = Layer.effect(MemBlock, Effect.gen(function* () {
    const checker = yield* BlockLimit;
    const proto = {
        load: (id: Db.Key) => Effect.sync (() => {
            id;
        }),
        make: (label: string, limit: number, decription?: string) => Effect.gen(function*() {
            yield* checker.check(label, limit);
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

export const CharMemBlock = Layer.provide(MemBlockLive, CharacterLimit);
export const WordMemBlock = Layer.provide(MemBlockLive, WordLimit);
export const TokenMemBlock = Layer.provide(MemBlockLive, TokenLimit);