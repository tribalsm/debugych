import { resultTarget } from '../resultTarget.js';
import { type Context, type Snapshot, type Connection, type PageAction, type Run } from '../contracts.js';
export interface ChatSource {
    label: string;
    page: PageAction;
    projectId: string;
    target: ReturnType<typeof resultTarget>;
}
export interface Case {
    name: string;
    status: string;
    traceback?: string;
    test_id?: string;
}
export interface ChatContext {
    scope: string;
    revision: string;
    projectName: string;
    projectId: string;
    rootId?: string;
    snapshot: Snapshot;
    connected: boolean;
    demo: boolean;
    historical: boolean;
    receivedAt?: number;
    original?: Run & {
        cases?: Case[];
    };
    cases: Case[];
    expected?: string;
    actual?: string;
    traceback?: string;
    description?: string;
    proposal?: string;
    changes: {
        path: string;
        before: string;
        after: string;
    }[];
    plan: {
        title: string;
        code: string;
        gherkin: string;
    }[];
    requirements: {
        key: string;
        text: string;
        quote: string;
    }[];
    sources: Partial<Record<PageAction, ChatSource>>;
}
/** Immutable, bounded project/run facts. No generated oracle, eval, or AI claims. */
export declare class CompanionContextBuilder {
    static build(c: Context, options: {
        backendUrl: string;
        connection: Connection;
        receivedAt?: number;
    }): ChatContext;
}
