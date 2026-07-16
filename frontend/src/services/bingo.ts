import api from "../api/client";
import type { GameHistoryPage, RoomSummary } from "../types/bingo";

const ROOM_NAME = "Ethiopian Bingo";

export async function getBingoHistory(
  limit = 10,
  offset = 0,
): Promise<GameHistoryPage> {
  const response = await api.get("/bingo/history", {
    params: { limit, offset },
  });

  return response.data;
}

export async function listRooms(): Promise<RoomSummary[]> {
  const response = await api.get("/bingo/rooms");

  return response.data.rooms;
}

export async function createRoom(name = ROOM_NAME): Promise<RoomSummary> {
  const response = await api.post("/bingo/rooms", { name });

  return response.data;
}

/**
 * Ethiopian Bingo runs one continuously-cycling public lobby (lobby -> game
 * -> winner -> lobby) that every player shares. The server owns that room's
 * identity and creates it atomically on first use, so the client just asks
 * for the canonical lobby. (A previous "list rooms, else create one" approach
 * raced: two players opening the app at the same time each created their own
 * room and could never see each other.)
 */
export async function findOrCreateRoom(): Promise<RoomSummary> {
  const response = await api.get("/bingo/lobby");

  return response.data;
}

export function bingoWebSocketUrl(roomId: string, token: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";

  return `${protocol}//${window.location.host}/ws/bingo/${roomId}?token=${encodeURIComponent(token)}`;
}
