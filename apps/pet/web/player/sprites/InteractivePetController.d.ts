import { type LocalReaction } from './manifest.js';
import { IdleBehaviorController, type BehaviorClock } from './IdleBehaviorController.js';
export interface InteractiveOptions extends BehaviorClock {
    now?: () => number;
    react: (kind: LocalReaction) => boolean;
    cancelReaction: () => void;
    canReact: () => boolean;
    togglePanel: () => void;
}
/** Local input only. It never invents or changes a task/system state. */
export declare class InteractivePetController {
    private options;
    private hoverTimer;
    private hovered;
    private dragging;
    private panel;
    private enabled;
    private visible;
    private disposed;
    private lastHover;
    private lastClick;
    readonly idle: IdleBehaviorController;
    private now;
    constructor(options: InteractiveOptions);
    private available;
    private clearHover;
    refresh(): void;
    enter(): void;
    leave(): void;
    beginDrag(): void;
    endGesture(dragged: boolean): void;
    click(): void;
    setPanel(value: boolean): void;
    setEnabled(value: boolean): void;
    setVisible(value: boolean): void;
    systemChanged(): void;
    dispose(): void;
}
