export const DEFAULT_SIZE=160;
export function normalizeSize(value){const n=Number(value);return Number.isFinite(n)?Math.min(260,Math.max(100,Math.round(n))):DEFAULT_SIZE;}
export function petDimensions(value,dpi=1){const h=normalizeSize(value);return {width:Math.round(h*5/6*dpi),height:Math.round(h*dpi)};}
