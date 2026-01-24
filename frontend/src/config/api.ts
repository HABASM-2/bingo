// src/config/api.ts

// Put your LAN IP or localhost here
// export const API_URL = "http://10.55.29.239:8000";
export const API_URL = "https://coraline-fabaceous-ungutturally.ngrok-free.dev";

export const getBingoWsUrl = (token?: string, stake: number = 20) => {
  const wsBase = API_URL.startsWith("https")
    ? API_URL.replace("https", "wss")
    : API_URL.replace("http", "ws");

  return token
    ? `${wsBase}/bingo/ws?token=${token}&stake=${stake}`
    : `${wsBase}/bingo/ws`;
};
