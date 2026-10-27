/** A deliberate hold or a drag must never open the popover on release. */
export function isShortClick(dx:number,dy:number,elapsedMs:number){return Math.hypot(dx,dy)<=5&&elapsedMs>=0&&elapsedMs<=700;}
