import { type CSSProperties } from 'react';
import { type PlayerInfo } from './SpritePlayer.js';
import { type SpriteManifest } from './manifest.js';
export interface SpritePlayerProps {
    manifest: SpriteManifest;
    state?: string;
    enabled?: boolean;
    paused?: boolean;
    className?: string;
    style?: CSSProperties;
    onInfo?: (info: PlayerInfo) => void;
}
/** React owns the lifecycle, Canvas owns frames. No per-frame React state update is required. */
export declare function ReactSpritePlayer({ manifest, state, enabled, paused, className, style, onInfo }: SpritePlayerProps): import("react").JSX.Element;
