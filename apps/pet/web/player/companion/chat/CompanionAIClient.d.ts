import { type ChatContext } from './CompanionContextBuilder.js';
import { type ChatAnswer } from './StructuredAnswers.js';
export interface AIPreview {
    available: boolean;
    provider: string;
    model: string;
    max_reserved_usd: number;
    max_calls: number;
    context_sha256: string;
    provider_fingerprint: string;
    context: unknown;
    notice: string;
    characters: number;
}
export type ConfirmAI = (p: AIPreview, signal: AbortSignal) => Promise<boolean>;
export interface AITransport {
    post: (path: string, body: unknown, signal: AbortSignal) => Promise<unknown>;
}
/** Server-only model access, one preview and one explicitly confirmed POST. No retries. */
export declare class CompanionAIClient {
    private transport;
    constructor(transport: AITransport);
    explain(question: string, c: ChatContext, signal: AbortSignal, confirm: ConfirmAI): Promise<ChatAnswer>;
}
