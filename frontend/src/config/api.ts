// src/config/api.ts

// Put your LAN IP or localhost here
export const API_URL = "http://10.55.29.239:8000";

// Optional WebSocket helper
export const getBingoWsUrl = (token?: string) => {
  const wsBase = API_URL.startsWith("https")
    ? API_URL.replace("https", "wss")
    : API_URL.replace("http", "ws");

  return token
    ? `${wsBase}/bingo/ws?token=${token}`
    : `${wsBase}/bingo/ws`;
};
