import { type ChatAnswer } from './StructuredAnswers.js';
import { type ChatContext, type ChatSource } from './CompanionContextBuilder.js';
import { type ConfirmAI } from './CompanionAIClient.js';
export interface Message {
    id: number;
    role: 'user' | 'assistant';
    text: string;
    scope: string;
    revision: string;
    answer?: ChatAnswer;
}
export interface ChatState {
    context: ChatContext | null;
    messages: Message[];
    pending: boolean;
    error: string;
    questions: string[];
    activity: 'facts' | 'ai' | null;
    retry: {
        question: string;
        ai: boolean;
    } | null;
}
export interface SavedConversation {
    scope: string;
    messages: Message[];
}
/** Memory-only bounded conversations, cancelled on context revision or scope change. */
export declare class CompanionChatController {
    private publish;
    private resolve;
    private resolveAI?;
    private retry;
    private activeQuestion;
    private context;
    private histories;
    private seq;
    private generation;
    private pending;
    private error;
    private disposed;
    private activity;
    constructor(publish: (state: ChatState) => void, resolve?: (q: string, c: ChatContext, signal: AbortSignal) => Promise<ChatAnswer>, resolveAI?: typeof this.resolve | undefined);
    private abort;
    update(context: ChatContext | null): void;
    private emit;
    send(question: string, ai?: boolean): Promise<void>;
    cancelPending(): void;
    clear(): void;
    exportHistory(): SavedConversation[];
    restoreHistory(value: unknown): void;
    dispose(): void;
}
/** Fits the existing Canvas/Tauri shell, with no additional renderer or LLM client. */
export declare class CompanionChat {
    private options;
    readonly element: HTMLElement;
    readonly controller: CompanionChatController;
    private log;
    private input;
    private questions;
    private status;
    private title;
    private send;
    private empty;
    private state;
    private draftScope;
    private rendered;
    readonly settingsElement: HTMLElement;
    private historyCheck;
    private retryButton;
    private aiEnabled;
    private aiAvailable;
    private aiMessage;
    private aiNote;
    private historySaving;
    private savedSignature;
    private storageReady;
    constructor(options: {
        openSource: (source: ChatSource) => Promise<void>;
        explain?: (q: string, c: ChatContext, signal: AbortSignal, confirm: ConfirmAI) => Promise<ChatAnswer>;
        activity?: (state: 'processing' | 'error' | 'idle') => void;
        saveHistory?: (enabled: boolean, history: SavedConversation[]) => Promise<void>;
    });
    private submit;
    private render;
    setAI(enabled: boolean, available: boolean, message: string): void;
    restoreStorage(saved: {
        enabled?: boolean;
        history?: unknown;
    }): void;
    private persist;
    private confirmAI;
    cancelPending(): void;
    update(c: ChatContext | null): void;
    dispose(): void;
}
