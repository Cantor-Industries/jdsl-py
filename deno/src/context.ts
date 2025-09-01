import { Context } from "effect";
import { type MemBlock,  } from "./memblock.ts";
export class ContextWindow extends Context.Tag("ContextWindow")<ContextWindow,ContextWindow.Window>() {}

export class SystemInstructions extends Context.Tag("SystemInstructions")<SystemInstructions, SystemInstructions.SystemInstructions> () {}

export declare namespace SystemInstructions {
    export interface Instructions {
        pry: MemBlock.Block
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
        systemInstructions: string;
        coreMemory: string;
        messages: string;
    }

    export interface ContextWindow {
        make: () => void;
        load: () => void;
        transform: () => void;
    }

}