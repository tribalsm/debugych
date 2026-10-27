import { AnimationStateController } from './AnimationStateController.js';
import { validateManifest, resolveClip } from './manifest.js';
export class SpritePlayer {
    canvas;
    controller;
    manifest;
    ctx;
    lastGood;
    previous;
    cache = new Map();
    loads = new Map();
    abort = new AbortController();
    timer = null;
    disposed = false;
    lastKey = '';
    lastInfo = '';
    lastState = '';
    transitionAt = -Infinity;
    request = 0;
    pendingPause = false;
    fallback = null;
    warning;
    now;
    schedule;
    cancel;
    load;
    notify;
    transitionMs;
    constructor(canvas, manifest, options = {}) {
        this.canvas = canvas;
        this.manifest = validateManifest(manifest);
        this.controller = new AnimationStateController(this.manifest);
        this.now = options.now ?? (() => performance.now());
        this.schedule = options.schedule ?? ((f, ms) => setTimeout(f, ms));
        this.cancel = options.cancel ?? (id => clearTimeout(id));
        this.load = options.load ?? (async (url, signal) => { const response = await fetch(url, { signal }); if (!response.ok)
            throw Error('HTTP ' + response.status); return createImageBitmap(await response.blob()); });
        this.notify = options.onInfo ?? (() => { });
        this.transitionMs = options.transitionMs ?? 160;
        const make = options.makeCanvas ?? (() => document.createElement('canvas'));
        this.lastGood = make();
        this.previous = make();
        for (const c of [canvas, this.lastGood, this.previous]) {
            c.width = manifest.width;
            c.height = manifest.height;
        }
        const ctx = canvas.getContext('2d', { alpha: true });
        if (!ctx)
            throw Error('Canvas 2D unavailable');
        this.ctx = ctx;
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
    }
    ensure(state) {
        const resolved = resolveClip(this.manifest, state).state;
        const cached = this.cache.get(resolved);
        if (cached)
            return Promise.resolve(cached);
        const pending = this.loads.get(resolved);
        if (pending)
            return pending;
        const clip = this.manifest.states[resolved];
        const task = this.load(clip.url, this.abort.signal).then(bitmap => { if (this.disposed) {
            bitmap.close?.();
            throw Error('Player disposed');
        } const maxX = Math.max(...clip.frameData.map(f => f.x + f.width)), maxY = Math.max(...clip.frameData.map(f => f.y + f.height)); if (bitmap.width < maxX || bitmap.height < maxY) {
            bitmap.close?.();
            throw Error('Atlas dimensions invalid');
        } this.cache.set(resolved, bitmap); return bitmap; }).finally(() => this.loads.delete(resolved));
        this.loads.set(resolved, task);
        return task;
    }
    async ready() {
        try {
            await this.ensure(this.manifest.defaultState);
        }
        catch {
            if (this.disposed)
                return;
            this.warning = 'Атлас idle недоступен: статичная замена';
            try {
                this.fallback = await this.load(this.manifest.fallbackUrl, this.abort.signal);
            }
            catch {
                this.warning = 'Не удалось загрузить изображения';
            }
        }
        if (!this.disposed)
            this.wake();
        else
            this.fallback?.close?.();
    }
    async play(state, repeat = false) {
        this.pendingPause = false;
        const id = ++this.request;
        resolveClip(this.manifest, state);
        if (!this.controller.isEnabled) {
            this.publish(this.controller.sample(this.now()));
            return false;
        }
        try {
            await this.ensure(state);
            if (this.disposed || id !== this.request) {
                this.evict([this.manifest.defaultState, this.controller.sample(this.now()).state]);
                return false;
            }
            this.warning = undefined;
            this.controller.play(state, this.now(), repeat);
            this.controller.setPaused(this.pendingPause, this.now());
            this.lastKey = '';
            this.wake();
            return true;
        }
        catch {
            if (this.disposed || id !== this.request)
                return false;
            this.warning = 'Не удалось загрузить ' + state + '. Сохранена последняя поза.';
            this.publish(this.controller.sample(this.now()));
            return false;
        }
    }
    react(kind) { if (this.disposed)
        return false; const accepted = this.controller.react(kind, this.now()); if (accepted) {
        this.lastKey = '';
        this.wake();
    } return accepted; }
    cancelReaction() { this.controller.cancelReaction(this.now()); this.wake(); }
    stop() { this.request++; this.controller.play(this.manifest.defaultState, this.now()); this.controller.setPaused(true, this.now()); this.lastKey = ''; this.transitionAt = -Infinity; this.wake(); }
    pause(value = true) { this.pendingPause = value; this.controller.setPaused(value, this.now()); this.wake(); }
    setEnabled(value) { this.request++; this.controller.setEnabled(value, this.now()); if (!value) {
        this.lastKey = '';
        this.transitionAt = -Infinity;
    } this.wake(); }
    setSuspended(value) { this.controller.setSuspended(value, this.now()); this.wake(); }
    publish(s) { const key = [s.requested, s.state, s.reaction, this.controller.isPaused, this.controller.isSuspended, this.controller.isEnabled, this.warning].join('|'); if (key === this.lastInfo)
        return; this.lastInfo = key; this.notify({ ...s, paused: this.controller.isPaused, suspended: this.controller.isSuspended, assetVersion: this.manifest.assetVersion, atlas: this.manifest.states[s.state].url ?? this.manifest.fallbackUrl, warning: this.warning }); }
    evict(keep) { for (const [state, image] of this.cache) {
        if (!keep.includes(state)) {
            image.close?.();
            this.cache.delete(state);
        }
    } }
    paint = () => {
        this.timer = null;
        if (this.disposed)
            return;
        if (this.controller.isSuspended) {
            this.publish(this.controller.sample(this.now()));
            return;
        }
        const time = this.now(), s = this.controller.sample(time), key = s.state + ':' + s.frame, image = this.cache.get(s.state);
        let transitioned = false;
        if (!image && !this.fallback) {
            this.publish(s);
            return;
        }
        if (image || this.fallback) {
            if (this.lastState && this.lastState !== s.state && this.controller.isEnabled) {
                const p = this.previous.getContext('2d');
                p.clearRect(0, 0, this.manifest.width, this.manifest.height);
                p.drawImage(this.canvas, 0, 0);
                this.transitionAt = time;
                transitioned = true;
            }
            const blend = this.controller.isEnabled && !this.controller.isPaused ? Math.min(1, (time - this.transitionAt) / this.transitionMs) : 1;
            if (key !== this.lastKey || blend < 1 || transitioned) {
                const g = this.lastGood.getContext('2d');
                g.clearRect(0, 0, this.manifest.width, this.manifest.height);
                if (image) {
                    const f = this.manifest.states[s.state].frameData[s.frame];
                    g.drawImage(image, f.x, f.y, f.width, f.height, 0, 0, this.manifest.width, this.manifest.height);
                }
                else
                    g.drawImage(this.fallback, 0, 0, this.manifest.width, this.manifest.height);
                this.ctx.clearRect(0, 0, this.manifest.width, this.manifest.height);
                if (blend < 1) {
                    this.ctx.globalAlpha = 1 - blend;
                    this.ctx.drawImage(this.previous, 0, 0);
                }
                this.ctx.globalAlpha = blend;
                this.ctx.drawImage(this.lastGood, 0, 0);
                this.ctx.globalAlpha = 1;
                this.lastKey = key;
                this.canvas.dataset.state = s.requested;
                this.canvas.dataset.frame = String(s.frame);
            }
            this.lastState = s.state;
            if (blend >= 1)
                this.evict([this.manifest.defaultState, s.state]);
        }
        this.publish(s);
        let delay = this.controller.nextDelay(time);
        if (time - this.transitionAt < this.transitionMs && this.controller.isEnabled && !this.controller.isPaused)
            delay = Math.min(delay, 1000 / 30);
        if (Number.isFinite(delay))
            this.timer = this.schedule(this.paint, delay);
    };
    wake() { if (this.timer !== null) {
        this.cancel(this.timer);
        this.timer = null;
    } if (!this.disposed)
        this.paint(); }
    dispose() { if (this.disposed)
        return; this.disposed = true; this.request++; this.abort.abort(); if (this.timer !== null)
        this.cancel(this.timer); this.timer = null; for (const image of this.cache.values())
        image.close?.(); this.cache.clear(); this.fallback?.close?.(); this.fallback = null; this.lastGood.width = this.lastGood.height = this.previous.width = this.previous.height = 1; }
}
