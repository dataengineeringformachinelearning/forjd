/**
 * Stable unique DOM ids for label / description / error association.
 */

export function createUidFactory(_namespace = 'suite'): (prefix: string) => string {
  let counter = 0;
  return (prefix: string): string => {
    counter += 1;
    return `${prefix}-${counter}`;
  };
}

/** FORJD adapter uid (mirrors vikingUid). */
export const forjdUid = createUidFactory('fj');
