/** A deliberate hold or a drag must never open the popover on release. */
export function isShortClick(dx, dy, elapsedMs) { return Math.hypot(dx, dy) <= 5 && elapsedMs >= 0 && elapsedMs <= 700; }
