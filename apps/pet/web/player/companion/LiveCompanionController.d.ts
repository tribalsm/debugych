import { type Snapshot, type FactEvent, type Context } from './contracts.js';
export interface LiveOptions {
    play: (clip: string, repeat?: boolean) => Promise<unknown> | unknown;
    notify: (event: FactEvent) => void;
    persistSeen: (keys: string[]) => void;
    seen?: string[];
}
/** State facts and event reactions are separate. Old snapshots hydrate silently. */
export declare class LiveCompanionController {
    private options;
    mode: 'live' | 'demo';
    snapshot: Snapshot | null;
    private scope;
    private primed;
    private animationKey;
    private seen;
    private visible;
    private notifications;
    private disposed;
    private reacting;
    private conversation;
    constructor(options: LiveOptions);
    resetScope(scope: string): void;
    setPreferences(notifications: boolean): void;
    setVisible(value: boolean): void;
    setConversation(value: 'processing' | 'error' | 'idle'): void;
    setMode(mode: 'live' | 'demo'): void;
    receive(context: Context): void;
    private receiveContextless;
    animationFinished(): void;
    refreshAnimation(): void;
    disconnected(): void;
    dispose(): void;
}
