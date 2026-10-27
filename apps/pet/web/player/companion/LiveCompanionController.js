import { deriveSnapshot, animationFor } from './deriveSnapshot.js';
/** State facts and event reactions are separate. Old snapshots hydrate silently. */
export class LiveCompanionController {
    options;
    mode = 'live';
    snapshot = null;
    scope = '';
    primed = false;
    animationKey = '';
    seen = new Set();
    visible = true;
    notifications = true;
    disposed = false;
    reacting = false;
    conversation = 'idle';
    constructor(options) {
        this.options = options;
        for (const key of (options.seen ?? []).slice(-128))
            this.seen.add(key);
    }
    resetScope(scope) { if (this.scope === scope)
        return; this.scope = scope; this.primed = false; this.snapshot = null; this.animationKey = ''; if (this.mode === 'live')
        void this.options.play('idle'); }
    setPreferences(notifications) { this.notifications = notifications; }
    setVisible(value) { this.visible = value; }
    setConversation(value) { if (this.conversation === value)
        return; this.conversation = value; if (this.reacting)
        return; this.animationKey = ''; if (this.snapshot)
        this.receiveContextless(this.snapshot, false); }
    setMode(mode) { if (mode === this.mode)
        return; this.mode = mode; this.primed = false; this.animationKey = ''; if (mode === 'live' && this.snapshot)
        this.receiveContextless(this.snapshot, false); }
    receive(context) {
        if (this.disposed)
            return;
        const snapshot = deriveSnapshot(context);
        this.snapshot = snapshot;
        const events = snapshot.events.filter(e => !this.seen.has(e.key));
        for (const e of snapshot.events)
            this.seen.add(e.key);
        while (this.seen.size > 128)
            this.seen.delete(this.seen.values().next().value);
        if (events.length)
            this.options.persistSeen([...this.seen]);
        const mayReact = this.primed && this.mode === 'live' && this.visible;
        if (mayReact && this.notifications)
            for (const e of events)
                this.options.notify(e);
        const reaction = mayReact && snapshot.state !== 'error' ? (events.some(e => e.kind === 'verification') ? 'success' : events.some(e => e.kind === 'bug_found') ? 'bug_found' : null) : null;
        if (reaction) {
            this.reacting = true;
            this.animationKey = 'event:' + snapshot.key;
            void this.options.play(reaction, false);
        }
        else
            this.receiveContextless(snapshot, false);
        this.primed = true;
    }
    receiveContextless(snapshot, eventReaction) {
        if (this.mode !== 'live' || this.disposed)
            return;
        let clip = animationFor(snapshot.state);
        const reaction = ['bug_found', 'success'].includes(snapshot.state);
        if (reaction && !eventReaction)
            clip = 'idle';
        if (['idle', 'bug_found', 'success'].includes(snapshot.state) && this.conversation !== 'idle')
            clip = this.conversation === 'processing' ? 'analyzing' : 'error';
        const key = clip + (reaction && eventReaction ? ':' + snapshot.key : '');
        if (key === this.animationKey)
            return;
        this.animationKey = key;
        void this.options.play(clip, clip === 'analyzing');
    }
    animationFinished() { if (!this.reacting || this.mode !== 'live' || !this.snapshot || this.disposed)
        return; this.reacting = false; this.animationKey = ''; this.receiveContextless(this.snapshot, false); }
    refreshAnimation() { this.animationKey = ""; if (this.snapshot)
        this.receiveContextless(this.snapshot, false); }
    disconnected() { this.reacting = false; this.conversation = 'idle'; if (this.mode === 'live') {
        this.animationKey = 'offline';
        void this.options.play('idle');
    } }
    dispose() { this.disposed = true; }
}
