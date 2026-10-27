import { type CompanionConfig, type Project, type Context, type Connection } from './contracts.js';
export declare class ApiError extends Error {
    readonly status: number;
    constructor(status: number, message: string);
}
export interface ApiTransport {
    get: (path: string, signal: AbortSignal) => Promise<unknown>;
}
export interface BackendUpdate {
    connection: Connection;
    message: string;
    projects?: Project[];
    context?: Context;
    health?: Record<string, unknown>;
    lastConfirmedAt?: number;
}
export interface AdapterOptions {
    transport: ApiTransport;
    publish: (u: BackendUpdate) => void;
    schedule?: (fn: () => void, ms: number) => unknown;
    cancel?: (id: unknown) => void;
    now?: () => number;
    isInspecting?: () => boolean;
    loadChatContext?: () => boolean;
}
/** One poll at a time, bounded backoff, abort on scope change. All requests are GET. */
export declare class DesktopPetBackendAdapter {
    private options;
    private timer;
    private abort;
    private generation;
    private failures;
    private connected;
    private disposed;
    private config;
    private schedule;
    private cancel;
    private now;
    constructor(options: AdapterOptions);
    configure(config: CompanionConfig): void;
    private current;
    private poll;
    stop(): void;
    dispose(): void;
}
