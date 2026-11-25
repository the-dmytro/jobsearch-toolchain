/** Top of the match score scale the dashboard shows. */
export const SCORE_MAX = 10;

/**
 * Brings an evaluation score onto the 0 to 10 scale. Most rows are already 0 to 10. Some were
 * written on a 0 to 100 scale, so a value above 10 is divided by ten. The result is clamped to
 * 0 to 10. Null, undefined and non-finite values give null.
 */
export function normalizeScore(score: number | null | undefined): number | null {
  if (score === null || score === undefined || !Number.isFinite(score)) return null;
  const scaled = score > SCORE_MAX ? score / 10 : score;
  return Math.min(SCORE_MAX, Math.max(0, scaled));
}
