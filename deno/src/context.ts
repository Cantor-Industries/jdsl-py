import { Context } from "effect";
import type { MemBlock, } from "./memblock.ts";

const SystemInstructionsTag = Context.Tag("SystemInstructions")<SystemInstructions, ContextProvider.SystemInstructions>();
export class SystemInstructions extends SystemInstructionsTag{};

const CoreMemoryTag = Context.Tag("CoreMemory")<CoreMemory, ContextProvider.CoreMemory>();
export class CoreMemory extends CoreMemoryTag {}

const MessagesTag = Context.Tag("Messages")<Messages, ContextProvider.Messages>();
export class Messages extends MessagesTag {};

const ContextProviderTag = Context.Tag("ContextProvider")<ContextProvider, ContextProvider.SystemInstructions>();
export class ContextProvider extends ContextProviderTag { };

const ContextWindowTag = Context.Tag("ContextWindow")<ContextWindow, ContextWindow.Window>();
export class ContextWindow extends ContextWindowTag { };

export declare namespace ContextProvider {
    export interface Instructions {
        instructions: MemBlock.Block[];
        memory: MemBlock.Block[];
        messages: MemBlock.Block[];
    }

    export interface SystemInstructions {
        make: () => void;
        load: () => void;
        update: () => void;
    }

    export interface CoreMemory {
        make: () => void;
        load: () => void;
        update: () => void;
    }

    export interface Messages {
        make: () => void;
        load: () => void;
        update: () => void;
    }
}

export declare namespace ContextWindow {
    export interface Window {
        capacity: number;
        used: number;
        systemInstructions: ContextProvider.Instructions['instructions'];
        coreMemory: ContextProvider.Instructions['memory'];
        messages: ContextProvider.Instructions['messages'];
    }

    export interface ContextWindow {
        make: () => void;
        load: () => void;
        transform: () => void;
    }

}