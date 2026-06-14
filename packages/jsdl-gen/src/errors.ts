import { Data } from "effect";

const PackageJsonErrorTag = Data.TaggedError("PackageJsonError")<{ msg: string }>;
export class PackageJsonError extends PackageJsonErrorTag { };

const EntryFileMissingErrorTag = Data.TaggedError("EntryFileMissingError")<{ msg: string }>;
export class EntryFileMissingError extends EntryFileMissingErrorTag { };

const TreeNotFoundErrorTag = Data.TaggedError("TreeNotFoundError")<{ msg: string }>;
export class TreeNotFoundError extends TreeNotFoundErrorTag { };

const ToolsNotFoundErrorTag = Data.TaggedError("ToolsNotFoundError")<{ msg: string }>;
export class ToolsNotFoundError extends ToolsNotFoundErrorTag { };