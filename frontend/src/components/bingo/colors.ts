/** B-I-N-G-O column colors for the Bright Games cartela grid. */

export interface ColumnColor {
  /** Solid header background (hex). */
  bg: string;
  /** Text color to sit on the solid background. */
  text: string;
}

export const COLUMN_COLORS: Record<string, ColumnColor> = {
  B: { bg: "#F5A623", text: "#ffffff" }, // amber / yellow
  I: { bg: "#22C55E", text: "#ffffff" }, // green
  N: { bg: "#3B82F6", text: "#ffffff" }, // blue
  G: { bg: "#EF4444", text: "#ffffff" }, // red
  O: { bg: "#7C3AED", text: "#ffffff" }, // purple
};

export function columnColorForNumber(n: number): ColumnColor {
  if (n <= 15) return COLUMN_COLORS.B;
  if (n <= 30) return COLUMN_COLORS.I;
  if (n <= 45) return COLUMN_COLORS.N;
  if (n <= 60) return COLUMN_COLORS.G;
  return COLUMN_COLORS.O;
}
