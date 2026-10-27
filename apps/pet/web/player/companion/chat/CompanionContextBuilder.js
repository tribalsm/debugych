import { deriveSnapshot } from '../deriveSnapshot.js';
import { resultTarget } from '../resultTarget.js';
import { redactChat } from './privacy.js';
const clip = (v, n = 1600) => typeof v === 'string' ? redactChat(v).slice(0, n) : '';
/** Immutable, bounded project/run facts. No generated oracle, eval, or AI claims. */
export class CompanionContextBuilder {
    static build(c, options) {
        const local = { ...c, runs: c.runs.filter(r => r.project_id === c.project.id), bugs: c.bugs.filter(b => b.project_id === c.project.id), fixes: c.fixes.filter(f => f.project_id === c.project.id) };
        const snapshot = structuredClone(deriveSnapshot(local));
        const original = local.runs.find(r => r.id === snapshot.bug?.run_id) ?? local.runs.find(r => r.operation === 'run' && (r.id === snapshot.rootId || r.parent_workflow_id === snapshot.rootId));
        const fullBug = snapshot.bug;
        const fullFix = snapshot.fix;
        const cases = Array.isArray(original?.cases) ? original.cases.slice(0, 80).map(v => ({ name: clip(v.name, 300), status: clip(v.status, 30), traceback: clip(v.traceback, 1200), test_id: clip(v.test_id, 40) })) : [];
        const tests = (c.tests ?? []).filter(t => t.project_id === c.project.id && t.result !== 'not_run' && ((original && t.last_run_id === original.id) || (!original && t.validation_id === snapshot.rootId)));
        const sources = {};
        for (const page of snapshot.actions)
            sources[page] = { label: ({ project: 'Проект', proof: 'Bug Proof', tests: 'Тесты', diff: 'Diff', verification: 'Fix & Verify', results: 'Отчёт' })[page], page, projectId: c.project.id, target: resultTarget(page, snapshot, local) };
        return { scope: [options.backendUrl, c.project.id, snapshot.rootId ?? 'empty'].join('|'), revision: snapshot.key, projectName: clip(c.project.name, 150), projectId: c.project.id, rootId: snapshot.rootId, snapshot, connected: options.connection === 'connected', demo: c.project.demo, historical: !!c.selectedRunId, receivedAt: options.receivedAt, original: original ? structuredClone(original) : undefined, cases, expected: clip(fullBug?.expected), actual: clip(fullBug?.actual), traceback: clip(fullBug?.traceback, 2500), description: clip(fullBug?.description), proposal: clip(fullFix?.explanation), changes: (fullFix?.changes ?? []).slice(0, 12).map(v => ({ path: clip(v.path, 160), before: clip(v.before, 2500), after: clip(v.after, 2500) })), plan: tests.slice(0, 12).map(t => ({ title: clip(t.title, 200), code: clip(t.code, 2500), gherkin: clip(t.gherkin, 1800) })), requirements: (c.requirements ?? []).filter(r => r.project_id === c.project.id && tests.some(t => t.requirement_id === r.id)).slice(0, 12).map(r => ({ key: clip(r.key, 40), text: clip(r.text, 1000), quote: clip(r.quote, 1000) })), sources };
    }
}
