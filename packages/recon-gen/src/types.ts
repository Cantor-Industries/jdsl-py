// deno-lint-ignore-file no-explicit-any
export type Children<A extends Tool> =
    | {
        [K in keyof A]: Action<A, K>;
    }[keyof A]
    | Selector<A>
    | Sequence<A>;

export interface Base {
    type: string;
}

export type MaybePromise<T> = T | Promise<T>;

export type ToolFunction = (...args: any[]) => MaybePromise<any>;

export type Tool = Record<string, ToolFunction>;

export type Action<
    A extends Tool,
    K extends keyof A
> =
    Base & {
        type: "action";
        call: K;
    } & (
        Parameters<A[K]> extends []
        ? { args?: never }
        : { args: Parameters<A[K]> }
    );


export interface Selector<A extends Tool = Tool> extends Base {
    type: "selector";
    children: Children<A>[];
}

export interface Sequence<A extends Tool = Tool> extends Base {
    type: "sequence";
    children: Children<A>[];
}

export interface Skill<A extends Tool = Tool> extends Base {
    type: "root";
    name?: string;
    child: Children<A>;
}

export interface PackageJson {
    main?: string;
    exports?: string | Record<string, unknown>;
}

export interface DenoJson {
    exports?: string | Record<string, unknown>;
}

async function evaluate<A extends Tool>(
    node: Children<A>,
    agent: A
): Promise<any> {
    switch (node.type) {
        case "action": {
            const fn = agent[node.call];
            // Any thrown error or rejection propagates naturally
            return await fn(...(node.args ?? []));
        }

        case "sequence": {
            let result: any;

            for (const child of node.children) {
                // If a child throws/rejects, this bubbles up automatically
                result = await evaluate(child, agent);
            }

            // Return value of the last child
            return result;
        }

        case "selector": {
            let lastError: unknown;

            for (const child of node.children) {
                try {
                    // First successful child wins
                    return await evaluate(child, agent);
                } catch (err) {
                    // Failed child → try next
                    lastError = err;
                }
            }

            // All children failed
            throw lastError ?? new Error("Selector: all children failed");
        }
    }
}
// deno-lint-ignore require-await
export async function run<A extends Tool>(
    root: Skill<A>,
    tools: A
) {
    return evaluate(root.child, tools);
}
