/** Only safe, user-facing messages cross the native/provider boundary. */
export declare class CompanionRequestError extends Error {
    readonly code: number | 'offline' | 'invalid';
    constructor(code: number | 'offline' | 'invalid', message?: string);
}
export declare function requestErrorMessage(error: unknown): string;
