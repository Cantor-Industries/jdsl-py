import { Context } from "effect";
import type { Behavior } from "./behavior.ts";

const SequenceTag = Context.Tag("Sequence")<Sequence, Behavior.Behavior>();
export class Sequence extends SequenceTag {};