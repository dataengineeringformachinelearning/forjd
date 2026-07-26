/**
 * Map `/ready` domain outcomes onto the shared fetch settle contract (ADR-0011).
 */

import type { FetchSettled } from './fetch-handle';
import type { ReadyProbeSettled, ReadyProbeSoftFailure } from '../ready/ready-probe';

/** Success payload for a ready probe — presence of `'ok'` means control plane ready. */
export type ReadyFetchData = 'ok';

export type ReadyFetchError = ReadyProbeSoftFailure;

/** Classify a settled probe into loading/error/success inputs for `runSettled`. */
export function settleReadyStatus(
  status: ReadyProbeSettled,
): FetchSettled<ReadyFetchData, ReadyFetchError> {
  if (status === 'ok') {
    return { ok: true, data: 'ok' };
  }
  return { ok: false, error: status };
}
