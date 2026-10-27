import { type Context, type Snapshot, type PageAction } from './contracts.js';
/** IDs are taken from the bound snapshot and its project, never from a title. */
export declare function resultTarget(page: PageAction, s: Snapshot, c: Context | null): {};
