// src/config/api.ts
export const API_URL = import.meta.env.VITE_API_URL;

export const getBingoWsUrl = (token?: string, stake: number = 20) => {
  const wsBase = API_URL.startsWith("https")
    ? API_URL.replace("https", "wss")
    : API_URL.replace("http", "ws");

  return token
    ? `${wsBase}/bingo/ws?token=${token}&stake=${stake}`
    : `${wsBase}/bingo/ws`;
};
