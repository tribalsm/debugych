export function validateManifest(input) {
    const m = input;
    if (!m || m.version !== 3 || !m.states?.[m.defaultState] || !Number.isInteger(m.width) || !Number.isInteger(m.height) || m.width < 1 || m.height < 1 || !m.fallbackUrl)
        throw Error('Invalid sprite manifest header');
    if (!m.anchor || ![m.anchor.x, m.anchor.y].every(Number.isFinite) || m.anchor.x < 0 || m.anchor.x > 1 || m.anchor.y < 0 || m.anchor.y > 1)
        throw Error('Invalid sprite anchor');
    for (const [name, c] of Object.entries(m.states)) {
        if (c.fallback) {
            let next = c.fallback;
            const seen = new Set([name]);
            while (next) {
                if (seen.has(next) || !m.states[next])
                    throw Error('Invalid fallback chain: ' + name);
                seen.add(next);
                next = m.states[next].fallback ?? '';
            }
            continue;
        }
        if (!c.url || !c.frameData?.length || c.frames !== c.frameData.length)
            throw Error('Missing sprite frames: ' + name);
        for (const f of c.frameData)
            if (![f.x, f.y, f.width, f.height, f.durationMs].every(Number.isFinite) || f.x < 0 || f.y < 0 || f.width !== m.width || f.height !== m.height || f.durationMs <= 0)
                throw Error('Invalid frame: ' + name);
        if (!Number.isInteger(c.neutralFrame ?? 0) || (c.neutralFrame ?? 0) < 0 || (c.neutralFrame ?? 0) >= c.frames)
            throw Error('Invalid neutral frame: ' + name);
        if (Math.abs(c.durationMs - c.frameData.reduce((s, f) => s + f.durationMs, 0)) > .05)
            throw Error('Invalid clip duration: ' + name);
        if (c.next && !m.states[c.next])
            throw Error('Invalid next state: ' + name);
    }
    if (m.states[m.defaultState].fallback)
        throw Error('Default state requires an atlas');
    for (const r of Object.values(m.reactions ?? {})) {
        const clip = m.states[r.source];
        if (!clip || clip.fallback || !r.frames.length)
            throw Error('Invalid reaction source');
        for (const f of r.frames)
            if (!Number.isInteger(f.index) || f.index < 0 || f.index >= clip.frames || !Number.isFinite(f.durationMs) || f.durationMs <= 0)
                throw Error('Invalid reaction frame');
    }
    return m;
}
export function resolveClip(m, state) {
    if (!m.states[state])
        throw Error('Unknown sprite state: ' + state);
    let name = state;
    let still = false;
    while (m.states[name].fallback) {
        still = true;
        name = m.states[name].fallback;
    }
    return { state: name, clip: m.states[name], static: still };
}
