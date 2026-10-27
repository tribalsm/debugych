export interface BehaviorClock {
    schedule: (f: () => void, ms: number) => unknown;
    cancel: (id: unknown) => void;
    random?: () => number;
}
/** One cancellable, irregular wake-up. Rendering remains owned by SpritePlayer. */
export declare class IdleBehaviorController {
    private act;
    private clock;
    private timer;
    private active;
    private disposed;
    constructor(act: () => void, clock: BehaviorClock);
    setActive(value: boolean): void;
    private clear;
    private plan;
    get pending(): boolean;
    dispose(): void;
}
