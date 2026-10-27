import { type Context, type Snapshot, type TaskState } from './contracts.js';
export declare function deriveSnapshot(c: Context): Snapshot;
export declare const animationFor: (state: TaskState) => string;
