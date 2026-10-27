/** IDs are taken from the bound snapshot and its project, never from a title. */
export function resultTarget(page, s, c) {
    const original = c?.runs.find(r => r.project_id === s.project.id && r.id === s.bug?.run_id)
        ?? c?.runs.find(r => r.project_id === s.project.id && r.parent_workflow_id === s.rootId && r.operation === 'run');
    const run = page === 'tests' ? original : page === 'verification' ? s.verification : page === 'results' ? (s.verification ?? original ?? s.run) : original;
    if (page === 'project')
        return {};
    return { runId: run?.id, ...(['proof', 'diff', 'verification'].includes(page) ? { bugId: s.bug?.id } : {}), ...(['diff', 'verification'].includes(page) ? { fixId: s.fix?.id } : {}) };
}
