import { IdleBehaviorController } from './IdleBehaviorController.js';
/** Local input only. It never invents or changes a task/system state. */
export class InteractivePetController {
    options;
    hoverTimer = null;
    hovered = false;
    dragging = false;
    panel = false;
    enabled = true;
    visible = true;
    disposed = false;
    lastHover = -Infinity;
    lastClick = -Infinity;
    idle;
    now;
    constructor(options) {
        this.options = options;
        this.now = options.now ?? (() => performance.now());
        this.idle = new IdleBehaviorController(() => { if (this.available())
            options.react('idle_variation'); }, options);
        this.refresh();
    }
    available() { return !this.disposed && this.enabled && this.visible && !this.dragging && !this.panel && this.options.canReact(); }
    clearHover() { if (this.hoverTimer !== null)
        this.options.cancel(this.hoverTimer); this.hoverTimer = null; }
    refresh() { this.idle.setActive(this.available() && !this.hovered); }
    enter() {
        if (this.hovered || this.disposed)
            return;
        this.hovered = true;
        this.refresh();
        if (!this.available() || this.now() - this.lastHover < 6500)
            return;
        this.hoverTimer = this.options.schedule(() => { this.hoverTimer = null; if (this.hovered && this.available()) {
            this.lastHover = this.now();
            this.options.react('hover');
        } }, 350);
    }
    leave() { if (!this.hovered)
        return; this.hovered = false; this.clearHover(); this.options.cancelReaction(); this.refresh(); }
    beginDrag() { this.dragging = true; this.clearHover(); this.options.cancelReaction(); this.refresh(); }
    endGesture(dragged) { this.dragging = false; if (!dragged)
        this.click(); this.refresh(); }
    click() { if (this.disposed)
        return; this.clearHover(); if (this.enabled && this.visible && this.options.canReact() && this.now() - this.lastClick >= 800) {
        this.lastClick = this.now();
        this.options.react('click');
    } this.options.togglePanel(); }
    setPanel(value) { this.panel = value; this.clearHover(); this.refresh(); }
    setEnabled(value) { this.enabled = value; if (!value) {
        this.clearHover();
        this.options.cancelReaction();
    } this.refresh(); }
    setVisible(value) { this.visible = value; if (!value) {
        this.hovered = false;
        this.clearHover();
        this.options.cancelReaction();
    } this.refresh(); }
    systemChanged() { this.clearHover(); this.options.cancelReaction(); this.refresh(); }
    dispose() { this.disposed = true; this.clearHover(); this.idle.dispose(); }
}
