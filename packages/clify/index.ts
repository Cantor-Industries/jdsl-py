import ts from "typescript";
import { Data, Effect } from "effect";
import { createBooleanAST, createNumericAST, createStringAST } from "./src/primitives.ts";
import { createCliAST, createCommandAST } from "./src/cli.ts";

interface ImportSpecifier {
	propertyName?: string;
	name: string;
	isType: boolean
}

interface ImportClause {
	namedImport?: string;
	namedBindings: ImportSpecifier[];
	node?: ts.ImportDeclaration;
	phaseModifier?: boolean
}

interface ImportDeclaration {
	[moduleSpecifier: string]: ImportClause
}

export class CliffyError extends Data.TaggedError("ClifyError")<{ msg: string }> { }
export class Clify extends Effect.Service<Clify>()(
    "Clify",
    {
        effect: Effect.gen(function* () {

            const createCli = (name: string, programFunction: ts.ArrowFunction | ts.FunctionExpression, pluginNames: string[]) => {
                const options: ts.VariableStatement[] = [];
                const imports: ImportDeclaration = {};

                const optionsNameList: {name: string, optional: boolean, restParameter: boolean}[] = [];
                let hasOptionalParameter = false;

                programFunction.parameters.forEach(parameter => {
                    const text = parameter.name.getFullText();
                    const optionalParameter = parameter.questionToken ? true : false;
                    const restParameter = parameter.dotDotDotToken ? true : false;

                    if (optionalParameter) {
                        hasOptionalParameter = true;
                        imports["effect"] = {namedBindings: [{name: "Option", isType: false}]};
                    }
                    const kind = parameter.type?.kind;
                    if (kind === ts.SyntaxKind.StringKeyword) {
                        options.push(createStringAST(text, optionalParameter, restParameter));
                        optionsNameList.push({name: text, optional: optionalParameter, restParameter: restParameter});
                    }
                    if (kind === ts.SyntaxKind.NumberKeyword) {
                        options.push(createNumericAST(text, optionalParameter, restParameter));
                        optionsNameList.push({name: text, optional: optionalParameter, restParameter: restParameter});
                    }
                    if (kind === ts.SyntaxKind.BooleanKeyword) {
                        options.push(createBooleanAST(text, optionalParameter, restParameter));
                        optionsNameList.push({name: text, optional: optionalParameter, restParameter: restParameter});
                    }
                })

                const command = createCommandAST(name, optionsNameList, hasOptionalParameter);
                imports["@effect/cli"] = {namedBindings: [{ name: "CliConfig", isType: false}, { name: "Command", isType: false }, { name: "Options", isType: false }]};

                const cli = createCliAST(name, "bun", pluginNames);
                imports["@effect/platform-bun"] = { namedBindings: [{name: "BunContext", isType: false}, {name: "BunRuntime", isType: false}]};

                return { cli, imports, options, command } as const
            };

            return { createCli } as const
        })
    }
) { }

