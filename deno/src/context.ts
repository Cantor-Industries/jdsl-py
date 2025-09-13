import { Context } from "effect";
import { type MemBlock,  } from "./memblock.ts";

const ContextWindowTag = Context.Tag("ContextWindow")<ContextWindow,ContextWindow.Window>();
export class ContextWindow extends ContextWindowTag {};

const SystemInstructionsTag = Context.Tag("SystemInstructions")<SystemInstructions, SystemInstructions.SystemInstructions> ();
export class SystemInstructions extends SystemInstructionsTag {};

export declare namespace SystemInstructions {
    export interface Instructions {
        instructions: MemBlock.Block[];
    }

    export interface SystemInstructions {
        make: () => void;
        load: () => void;
        update: () => void;
    }
}

export declare namespace ContextWindow {
    export interface Window {
        capacity: number;
        used: number;
        systemInstructions: SystemInstructions.Instructions['instructions'];
        coreMemory: string;
        messages: string;
    }

    export interface ContextWindow {
        make: () => void;
        load: () => void;
        transform: () => void;
    }

}