import type { RoomStatus } from "../../types/bingo";

/**
 * Home “live now” metric: boards selected/taken (occupancy), not unique players.
 * Returns `null` outside lobby / in-progress so Home does not show a stale count.
 */
export function bingoHomeLiveBoardCount(
  status: RoomStatus | null | undefined,
  takenBoards: number[] | null | undefined,
): number | null {
  if (status !== "lobby" && status !== "in_progress") return null;
  return takenBoards?.length ?? 0;
}
