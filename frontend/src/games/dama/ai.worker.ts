/// <reference lib="webworker" />

import { searchBestMove } from "./ai";
import type { AiWorkerInbound, AiWorkerResult } from "./aiMessages";

let activeId: number | null = null;
let cancelFlag = false;

self.onmessage = (event: MessageEvent<AiWorkerInbound>) => {
  const msg = event.data;
  if (msg.type === "cancel") {
    if (activeId === msg.id) cancelFlag = true;
    return;
  }

  if (msg.type !== "search") return;

  activeId = msg.id;
  cancelFlag = false;

  const result = searchBestMove(msg.board, msg.side, {
    difficulty: msg.difficulty,
    timeBudgetMs: msg.timeBudgetMs,
    historyHashes: msg.historyHashes,
    shouldCancel: () => cancelFlag || activeId !== msg.id,
  });

  if (activeId === msg.id) {
    const out: AiWorkerResult = { type: "result", id: msg.id, result };
    self.postMessage(out);
  }
  if (activeId === msg.id) activeId = null;
};
