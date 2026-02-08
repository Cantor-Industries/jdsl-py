import { Data } from "effect";

export class AiError extends Data.TaggedError("AiError")<{msg: string}>{}