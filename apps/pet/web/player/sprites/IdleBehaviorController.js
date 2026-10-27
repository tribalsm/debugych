/** One cancellable, irregular wake-up. Rendering remains owned by SpritePlayer. */
export class IdleBehaviorController {
    act;
    clock;
    timer = null;
    active = false;
    disposed = false;
    constructor(act, clock) {
        this.act = act;
        this.clock = clock;
    }
    setActive(value) { if (this.disposed || value === this.active)
        return; this.active = value; this.clear(); if (value)
        this.plan(); }
    clear() { if (this.timer !== null)
        this.clock.cancel(this.timer); this.timer = null; }
    plan() { this.timer = this.clock.schedule(() => { this.timer = null; if (!this.active || this.disposed)
        return; this.act(); this.plan(); }, 12000 + (this.clock.random ?? Math.random)() * 15000); }
    get pending() { return this.timer !== null; }
    dispose() { this.disposed = true; this.active = false; this.clear(); }
}
