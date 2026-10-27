export interface Frame {
    x: number;
    y: number;
    width: number;
    height: number;
    durationMs: number;
}
export interface Clip {
    name: string;
    label: string;
    frames: number;
    url?: string;
    frameData?: Frame[];
    durationMs: number;
    loop: boolean;
    next?: string;
    neutralFrame?: number;
    fallback?: string;
    availability: 'animated' | 'static-fallback';
    sourceAction?: string;
}
export type LocalReaction = 'hover' | 'click' | 'idle_variation';
export interface Reaction {
    source: string;
    frames: {
        index: number;
        durationMs: number;
    }[];
}
export interface SpriteManifest {
    version: 3;
    assetVersion: string;
    width: number;
    height: number;
    fps: number;
    columns: number;
    anchor: {
        x: number;
        y: number;
    };
    defaultState: string;
    fallbackUrl: string;
    states: Record<string, Clip>;
    reactions?: Partial<Record<LocalReaction, Reaction>>;
}
export declare function validateManifest(input: unknown): SpriteManifest;
export declare function resolveClip(m: SpriteManifest, state: string): {
    state: string;
    clip: Clip;
    static: boolean;
};
