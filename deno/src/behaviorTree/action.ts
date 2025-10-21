import { Context } from "effect";
import type { Behavior } from "./behavior.ts";

const ActionTag = Context.Tag("Action")<Action, Behavior.Behavior>();
export class Action extends ActionTag {};