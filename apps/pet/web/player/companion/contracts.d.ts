export type TaskState = 'idle' | 'analyzing' | 'generating' | 'testing' | 'bug_found' | 'fixing' | 'verifying' | 'success' | 'error' | 'offline';
export type Connection = 'connecting' | 'connected' | 'offline' | 'authorization_required' | 'server_error' | 'incompatible';
export interface Project {
    id: string;
    name: string;
    demo: boolean;
    created_at: string;
}
export interface Assessment {
    original_fixed?: boolean;
    regressions_absent?: boolean;
    all_regression_passed?: boolean;
    reproduced_again?: boolean;
    requirement_reviewed?: boolean;
    infrastructure_excluded?: boolean;
}
export interface Run {
    id: string;
    project_id: string;
    created_at: string;
    operation: string;
    status: string;
    stage?: string;
    parent_workflow_id?: string;
    bug_id?: string;
    fix_id?: string;
    verified?: boolean;
    patch_sha256?: string;
    passed?: number;
    failed?: number;
    errors?: number;
    error?: string;
    assessment?: Assessment;
    review?: {
        run_id?: string;
        test_sha256?: string;
    };
    trusted_demo?: boolean;
}
export interface Bug {
    id: string;
    project_id: string;
    run_id?: string;
    proof_id?: string;
    test_sha256?: string;
    status: string;
    title: string;
    description?: string;
    file?: string;
    line?: number;
    current_fix_id?: string;
}
export interface Fix {
    id: string;
    project_id: string;
    bug_id: string;
    proof_id?: string;
    diff: string;
    explanation?: string;
    verified: boolean;
    applied: boolean;
    verification_id?: string;
    patch_sha256?: string;
    assessment?: Assessment;
    created_at: string;
}
export interface TestCase {
    id: string;
    project_id: string;
    title: string;
    requirement_id?: string;
    last_run_id?: string;
    validation_id?: string;
    code?: string;
    gherkin?: string;
    framework?: string;
    result?: string;
}
export interface Requirement {
    id: string;
    project_id: string;
    text: string;
    key?: string;
    quote?: string;
    source?: string;
}
export interface Context {
    project: Project;
    runs: Run[];
    bugs: Bug[];
    fixes: Fix[];
    selectedRunId?: string;
    tests?: TestCase[];
    requirements?: Requirement[];
}
export type PageAction = 'project' | 'proof' | 'tests' | 'diff' | 'verification' | 'results';
export interface FactEvent {
    key: string;
    title: string;
    kind: 'analysis_done' | 'bug_found' | 'patch_ready' | 'verification' | 'execution_error';
}
export interface Snapshot {
    state: TaskState;
    key: string;
    project: Project;
    rootId?: string;
    run?: Run;
    bug?: Bug;
    fix?: Fix;
    verification?: Run;
    title: string;
    explanation: string;
    phrase: string;
    events: FactEvent[];
    actions: PageAction[];
    trustedDemo: boolean;
}
export interface CompanionConfig {
    backendUrl: string;
    frontendUrl: string;
    projectId: string;
    runId: string;
    enabled: boolean;
    notifications: boolean;
    phrases: boolean;
    contextualAIEnabled: boolean;
}
export declare const defaults: CompanionConfig;
export declare const uuid: (s: unknown) => s is string;
export declare function baseUrl(value: string): string;
