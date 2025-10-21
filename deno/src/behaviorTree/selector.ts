import { Context } from "effect";
import type { Behavior } from "./behavior.ts";

const SelectorTag = Context.Tag("Selector")<Selector, Behavior.Behavior>();
export class Selector extends SelectorTag {};