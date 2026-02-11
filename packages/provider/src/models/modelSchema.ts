import { Schema } from "effect"

const DateString = Schema.String.pipe(
    Schema.pattern(/^\d{4}-\d{2}(-\d{2})?$/)
);

const InterleavedObject = Schema.Struct({
    field: Schema.Literal("reasoning_content", "reasoning_details")
});

const InterleavedSchema = Schema.Union(
    Schema.Boolean,
    InterleavedObject
);

const CostSchema = Schema.Struct({
    input: Schema.Number,
    output: Schema.Number,

    reasoning: Schema.optional(Schema.Number),
    cache_read: Schema.optional(Schema.Number),
    cache_write: Schema.optional(Schema.Number),
    input_audio: Schema.optional(Schema.Number),
    output_audio: Schema.optional(Schema.Number)
});

const LimitSchema = Schema.Struct({
    context: Schema.Number,
    input: Schema.optional(Schema.Number),
    output: Schema.Number
});

const ModalitiesSchema = Schema.Struct({
    input: Schema.Array(Schema.String),
    output: Schema.Array(Schema.String)
});

const StatusSchema = Schema.Literal(
    "alpha",
    "beta",
    "deprecated"
);

const ModelSchema = Schema.Struct({
    name: Schema.String,
    id: Schema.String,
    family: Schema.optional(Schema.String),

    attachment: Schema.Boolean,
    reasoning: Schema.Boolean,
    tool_call: Schema.Boolean,
    structured_output: Schema.optional(Schema.Boolean),
    temperature: Schema.optional(Schema.Boolean),

    knowledge: Schema.optional(DateString),
    release_date: DateString,
    last_updated: DateString,
    open_weights: Schema.Boolean,

    interleaved: Schema.optional(InterleavedSchema),

    cost: Schema.optional(CostSchema),
    limit: LimitSchema,
    modalities: ModalitiesSchema,
    status: Schema.optional(StatusSchema)
});
export interface Model extends Schema.Schema.Type<typeof ModelSchema> { };

const ProviderSchema = Schema.Struct({
    id: Schema.String,
    name: Schema.String,
    npm: Schema.String,
    env: Schema.Array(Schema.String),
    doc: Schema.String,
    api: Schema.optional(Schema.String),
    models: Schema.Record({key: Schema.String, value: ModelSchema})
});
export interface Provider extends Schema.Schema.Type<typeof ProviderSchema> { };

export const ModelsDevSchema = Schema.Record({key: Schema.String, value: ProviderSchema});
export interface ModelProviders extends Schema.Schema.Type<typeof ModelsDevSchema> { };
