import { jsx as _jsx } from "react/jsx-runtime";
import { useEffect, useRef } from 'react';
import { SpritePlayer } from './SpritePlayer.js';
/** React owns the lifecycle, Canvas owns frames. No per-frame React state update is required. */
export function ReactSpritePlayer({ manifest, state, enabled = true, paused = false, className, style, onInfo }) {
    const canvas = useRef(null), player = useRef(null), info = useRef(onInfo);
    info.current = onInfo;
    useEffect(() => { const p = new SpritePlayer(canvas.current, manifest, { onInfo: v => info.current?.(v) }); player.current = p; void p.ready(); const visibility = () => p.setSuspended(document.hidden); document.addEventListener('visibilitychange', visibility); visibility(); return () => { document.removeEventListener('visibilitychange', visibility); p.dispose(); player.current = null; }; }, [manifest]);
    useEffect(() => { if (state)
        void player.current?.play(state); }, [manifest, state, enabled]);
    useEffect(() => { const query = matchMedia('(prefers-reduced-motion:reduce)'); const update = () => player.current?.setEnabled(enabled && !query.matches); update(); query.addEventListener('change', update); return () => query.removeEventListener('change', update); }, [manifest, enabled]);
    useEffect(() => player.current?.pause(paused), [manifest, paused]);
    return _jsx("canvas", { ref: canvas, className: className, style: style, "aria-label": "\u0414\u0435\u0431\u0430\u0433\u044B\u0447" });
}
