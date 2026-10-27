import { AnimationStateController, type Sample } from './AnimationStateController.js';
import { type SpriteManifest, type LocalReaction } from './manifest.js';
type Bitmap = CanvasImageSource & {
    width: number;
    height: number;
    close?: () => void;
};
export interface PlayerInfo extends Sample {
    paused: boolean;
    suspended: boolean;
    assetVersion: string;
    atlas: string;
    warning?: string;
}
export interface PlayerOptions {
    now?: () => number;
    schedule?: (f: () => void, ms: number) => unknown;
    cancel?: (id: unknown) => void;
    makeCanvas?: () => HTMLCanvasElement;
    load?: (url: string, signal: AbortSignal) => Promise<Bitmap>;
    onInfo?: (info: PlayerInfo) => void;
    transitionMs?: number;
}
export declare class SpritePlayer {
    private canvas;
    readonly controller: AnimationStateController;
    readonly manifest: SpriteManifest;
    private ctx;
    private lastGood;
    private previous;
    private cache;
    private loads;
    private abort;
    private timer;
    private disposed;
    private lastKey;
    private lastInfo;
    private lastState;
    private transitionAt;
    private request;
    private pendingPause;
    private fallback;
    private warning?;
    private now;
    private schedule;
    private cancel;
    private load;
    private notify;
    private transitionMs;
    constructor(canvas: HTMLCanvasElement, manifest: SpriteManifest, options?: PlayerOptions);
    private ensure;
    ready(): Promise<void>;
    play(state: string, repeat?: boolean): Promise<boolean>;
    react(kind: LocalReaction): boolean;
    cancelReaction(): void;
    stop(): void;
    pause(value?: boolean): void;
    setEnabled(value: boolean): void;
    setSuspended(value: boolean): void;
    private publish;
    private evict;
    private paint;
    private wake;
    dispose(): void;
}
export {};
