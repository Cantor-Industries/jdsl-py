import { Context, Data, Effect, Either, Layer } from "effect";
import { Db, DenoKVDB } from "@floq/kv";
import { DenoKVStore } from "@floq/kv/store";
// import { MemBlock } from "recon/block";

const KnowledgeBaseTag = Context.Tag("KnowledgeBaseTag")<KnowledgeBase, KnowlegeBase.Kb>();
export class KnowledgeBase extends KnowledgeBaseTag { };

const KnowledgeBaseNotFoundTag = Data.TaggedError("KnowledgeBaseNotFound")<{msg: string}>;
export class KnowledgeBaseNotFound extends KnowledgeBaseNotFoundTag {};

const KnowledgeBaseFetchErrorTag = Data.TaggedError("KnowledgeBaseFetchError")<{msg: string}>;
export class KnowledgeBaseFetchError extends KnowledgeBaseFetchErrorTag {};

const KnowledgeBaseSaveErrorTag = Data.TaggedError("KnowledgeBaseSaveError")<{msg: string}>;
export class KnowledgeBaseSaveError extends KnowledgeBaseSaveErrorTag {};

export declare namespace KnowlegeBase {
    export interface Kb {
        open: (name: string) => Effect.Effect<void, KnowledgeBaseNotFound, never>;
        close: () => Effect.Effect<void, never, never>;
        fetch: <T>(key: string[]) => Effect.Effect<T, KnowledgeBaseFetchError, never>;
        save: <T>(key: Db.Key, value: T) => Effect.Effect<void, KnowledgeBaseSaveError, never>;
    }
}

const DenoKnowledgeBase = Layer.effect(KnowledgeBase, Effect.gen(function* () {
    const db = yield* Effect.provide(Db, DenoKVDB);
    const proto = {
        open: (name: string) => Effect.gen(function* () {
            const openorfail = yield* Effect.either(db.connect(name));
            if (Either.isLeft(openorfail)) {
                yield* new KnowledgeBaseNotFound({msg: `Knowledgebase ${name} not found`});
            }
        }),
        close: () => Effect.gen(function* () {
            yield* db.close();
        }),
        fetch: <T>(key: Db.Key) => Effect.gen(function* () {
            const blockorfail = yield* Effect.either(db.get<T>(key));
            if (Either.isLeft(blockorfail)) {
                return yield* new KnowledgeBaseFetchError({msg: `Knowledgebase missing value for key: ${key}`})
            } else {
                return blockorfail.right
            }
        }),
        save: <T>(key: Db.Key, value: T) => Effect.gen(function* () {
            const setorfail = yield* Effect.either(db.set(key, value));
            if (Either.isLeft(setorfail)) {
                yield* new KnowledgeBaseSaveError({msg: `Failed to save value: ${value} for key: ${key}`})
            }
        })
    }
    return proto;
}))

export const connect = (kbName: string) => Effect.gen(function* () {
    const kb = yield* Effect.provide(KnowledgeBase, DenoKnowledgeBase);
    yield* kb.open(kbName)
    return kb;
}).pipe(Effect.provide(DenoKVStore));

// export const getBlock = (key: Db.Key, db: Db.Db) => Layer.effect(MemBlock, Effect.gen(function* () {
//     const proto = {
//         load: (key: Db.Key) => Effect.gen(function* () {

//         })
//     }
//     return proto;
// }))