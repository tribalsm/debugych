import { type ChatContext, type ChatSource } from './CompanionContextBuilder.js';
export interface ChatAnswer {
    text: string;
    kind: 'facts' | 'limitation' | 'llm';
    sources: ChatSource[];
    scope: string;
    revision: string;
}
export type Intent = 'found' | 'why' | 'location' | 'proof' | 'patch' | 'applied' | 'failed' | 'results' | 'status' | 'plan' | 'unknown';
/** Explicit intents over evidence. Never represented as an LLM response. */
export declare function intentFor(question: string): Intent;
export declare function quickQuestions(c: ChatContext | null): string[];
export declare function answerFromFacts(question: string, c: ChatContext): ChatAnswer;
