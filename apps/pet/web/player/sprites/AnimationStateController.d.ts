import { type SpriteManifest, type LocalReaction } from './manifest.js';
export interface Sample {
    requested: string;
    state: string;
    frame: number;
    finished: boolean;
    reaction?: LocalReaction;
}
export declare class AnimationStateController {
    readonly manifest: SpriteManifest;
    requested: string;
    private elapsed;
    private last;
    private paused;
    private suspended;
    private enabled;
    private repeat;
    private local;
    constructor(manifest: SpriteManifest);
    private tick;
    play(state: string, now: number, repeat?: boolean): void;
    setPaused(value: boolean, now: number): void;
    setSuspended(value: boolean, now: number): void;
    setEnabled(value: boolean, now: number): void;
    react(kind: LocalReaction, now: number): boolean;
    cancelReaction(now: number): void;
    get isReacting(): boolean;
    get isSuspended(): boolean;
    get isEnabled(): boolean;
    get isPaused(): boolean;
    sample(now: number): Sample;
    nextDelay(now: number): number;
}
