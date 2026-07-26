/**
 * Suite semantic tones for forjd-ui feedback primitives.
 * Mirrors viking-ui VikingTone without importing the Viking Angular barrel.
 */
export type FjTone = 'accent' | 'secondary' | 'success' | 'warning' | 'danger' | 'info' | 'muted';

/** @deprecated Use FjTone — kept for one release of adapter rename. */
export type VikingTone = FjTone;
