export type MaybePromise<T> = T | Promise<T>;
export type ToolFunction = (...args: any[]) => MaybePromise<any>;
export type Tool = Record<string, ToolFunction>;

export interface Base {
  type: string;
}

type CallName<A> = A extends Tool ? keyof A & string : string;

export interface Action<A = undefined> extends Base {
  type: "action";
  call: CallName<A>;
  args?: unknown[];
}

export type Child<A = undefined> =
  | Action<A>
  | Sequence<A>
  | Selector<A>;

export interface Sequence<A = undefined> extends Base {
  type: "sequence";
  children: Child<A>[];
}

export interface Selector<A = undefined> extends Base {
  type: "selector";
  children: Child<A>[];
}

export interface Skill<A = undefined> {
  type: "root";
  name?: string;
  description?: string;
  child: Child<A>;
}


export interface PackageJson {
    main?: string;
    exports?: string | Record<string, unknown>;
}

export interface DenoJson {
    exports?: string | Record<string, unknown>;
}