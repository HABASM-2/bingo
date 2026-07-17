/** Shared Dama timing constants (seconds). */
export const DAMA_TURN_TIMEOUT_SEC = 120;
/** AI mid-game resume TTL — long enough to rejoin, not forever. */
export const DAMA_AI_SESSION_TTL_SEC = 20 * 60;

/** Minimum / maximum play stake (ETB). */
export const DAMA_MIN_STAKE = 5;
export const DAMA_MAX_STAKE = 500;

export function isValidDamaStake(stake: string): boolean {
  const n = Number(stake);
  return Number.isFinite(n) && n >= DAMA_MIN_STAKE && n <= DAMA_MAX_STAKE;
}
