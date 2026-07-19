/**
 * Lotto WAVs served from Vite public at `/audio_lotto/`:
 * - `1.wav` … `25.wav` — number called when the wheel settles on a winner
 * - `start.wav` — first spin of a round actually begins (cruise)
 * - `first_winner.wav` / `second_winner.wav` / `third_winner.wav` — place
 *   announcement, played before that winner’s number clip
 * - `next.wav` — after third winner + number, before the next-round transition
 *
 * Playback uses direct `/audio_lotto/*.wav` URLs (reliable in Telegram WebView).
 * Cache API is only used for best-effort HTTP prefetch — not blob ObjectURLs.
 */

const BASE = "/audio_lotto";
const AUDIO_CACHE_NAME = "bright-games-lotto-audio-v1";

const WINNER_CLIPS = {
  1: "first_winner",
  2: "second_winner",
  3: "third_winner",
} as const;

export type LottoNamedClip =
  | "start"
  | "first_winner"
  | "second_winner"
  | "third_winner"
  | "next";

/** Padding after `next.wav` before callers treat the sequence as done. */
export const LOTTO_AFTER_NEXT_PAD_MS = 1000;

/**
 * Conservative mute/silent estimates (ms) so timing stays aligned when muted.
 * Place clips ≈ measured WAV lengths; number covers longest (`25.wav` ≈ 2.84s).
 * Only used when the user explicitly mutes — never as the normal play path.
 */
const PLACE_ESTIMATE_MS: Record<number, number> = {
  1: 2100,
  2: 2500,
  3: 2300,
};
const NUMBER_ESTIMATE_MS = 2900;
const NEXT_ESTIMATE_MS = 2900;

const ALL_SOURCES = [
  `${BASE}/start.wav`,
  `${BASE}/first_winner.wav`,
  `${BASE}/second_winner.wav`,
  `${BASE}/third_winner.wav`,
  `${BASE}/next.wav`,
  ...Array.from({ length: 25 }, (_, i) => `${BASE}/${i + 1}.wav`),
];

export type LottoWinnerRank = keyof typeof WINNER_CLIPS;

export function lottoNumberSrc(number: number): string {
  return `${BASE}/${number}.wav`;
}

export function lottoNamedSrc(name: LottoNamedClip): string {
  return `${BASE}/${name}.wav`;
}

export function lottoWinnerClipSrc(rank: number): string | null {
  const name = WINNER_CLIPS[rank as LottoWinnerRank];
  return name ? lottoNamedSrc(name) : null;
}

/** Structural delay for place→number→(next) when the user explicitly muted. */
export function estimateWinnerRevealMs(
  rank: number,
  includeNext = rank === 3,
): number {
  const place = PLACE_ESTIMATE_MS[rank] ?? PLACE_ESTIMATE_MS[3];
  const next = includeNext ? NEXT_ESTIMATE_MS + LOTTO_AFTER_NEXT_PAD_MS : 0;
  return place + NUMBER_ESTIMATE_MS + next;
}

const player = new Audio();
player.preload = "auto";
player.muted = false;
player.volume = 1;

let playToken = 0;
let queueRunning = false;
const clipQueue: string[] = [];
let queueWaiters: Array<() => void> = [];
const elementWarmCache = new Map<string, HTMLAudioElement>();
let audioUnlocked = false;

function notifyQueueIdle(): void {
  const waiters = queueWaiters;
  queueWaiters = [];
  for (const resolve of waiters) resolve();
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

/** Keep the shared element audible — unlock briefly uses volume 0. */
function ensureAudible(): void {
  player.muted = false;
  if (player.volume < 0.5) player.volume = 1;
}

async function cacheAudio(
  src: string,
  signal?: AbortSignal,
): Promise<Response | null> {
  if (!("caches" in window)) return null;
  try {
    const cache = await caches.open(AUDIO_CACHE_NAME);
    const cached = await cache.match(src);
    if (cached) return cached;

    const response = await fetch(src, { signal, cache: "force-cache" });
    if (!response.ok) return null;
    const contentType = response.headers.get("content-type") ?? "";
    // Some static hosts omit content-type for WAVs; reject only clear non-audio.
    if (
      contentType
      && !contentType.startsWith("audio/")
      && !contentType.includes("octet-stream")
    ) {
      return null;
    }
    await cache.put(src, response.clone());
    return response;
  } catch {
    return null;
  }
}

async function playOne(src: string, token: number): Promise<boolean> {
  if (token !== playToken) return false;
  try {
    // Direct path URLs — blob ObjectURLs from Cache API often fail silently
    // inside Telegram / iOS WebViews.
    ensureAudible();
    player.pause();
    player.src = src;
    player.currentTime = 0;
    await player.play();
    if (token !== playToken) {
      player.pause();
      return false;
    }
    await new Promise<void>((resolve) => {
      const finish = () => {
        player.removeEventListener("ended", finish);
        player.removeEventListener("error", finish);
        resolve();
      };
      player.addEventListener("ended", finish);
      player.addEventListener("error", finish);
    });
    return token === playToken;
  } catch {
    // Autoplay policy / missing file — never brick the UI.
    ensureAudible();
    return false;
  }
}

async function drainQueue(token: number): Promise<void> {
  if (queueRunning) return;
  queueRunning = true;
  try {
    while (clipQueue.length > 0 && token === playToken) {
      const next = clipQueue.shift();
      if (!next) break;
      await playOne(next, token);
    }
  } finally {
    queueRunning = false;
    if (clipQueue.length > 0 && token === playToken) {
      void drainQueue(token);
    } else {
      notifyQueueIdle();
    }
  }
}

/**
 * Enqueue clips; they play in order without overlapping.
 * Resolves when the queue is idle after these clips (interrupted stop resolves early).
 */
export function enqueueLottoClips(
  ...sources: Array<string | null | undefined>
): Promise<void> {
  const clipped = sources.filter((src): src is string => Boolean(src));
  if (!clipped.length) return Promise.resolve();
  clipQueue.push(...clipped);
  return new Promise<void>((resolve) => {
    queueWaiters.push(resolve);
    void drainQueue(playToken);
  });
}

/** Stop playback and clear any pending queue. */
export function stopLottoAudio(): void {
  playToken += 1;
  clipQueue.length = 0;
  queueRunning = false;
  notifyQueueIdle();
  try {
    player.pause();
    player.currentTime = 0;
  } catch {
    /* ignore */
  }
}

export function playLottoStart(): void {
  ensureAudible();
  void enqueueLottoClips(lottoNamedSrc("start"));
}

/**
 * Winner place clip, then the winning number (e.g. first_winner → 12).
 * After third place + number, also plays `next.wav` and a short pad.
 * Resolves when the full sequence finishes (or after mute estimate when `silent`).
 *
 * `silent` is only for an explicit user mute — not the default playback path.
 */
export async function playLottoWinnerReveal(
  rank: number,
  number: number,
  options?: { silent?: boolean },
): Promise<void> {
  const includeNext = rank === 3;
  if (options?.silent) {
    await delay(estimateWinnerRevealMs(rank, includeNext));
    return;
  }

  ensureAudible();
  const numberSrc =
    Number.isInteger(number) && number >= 1 && number <= 25
      ? lottoNumberSrc(number)
      : null;
  await enqueueLottoClips(
    lottoWinnerClipSrc(rank),
    numberSrc,
    includeNext ? lottoNamedSrc("next") : null,
  );
  if (includeNext) {
    await delay(LOTTO_AFTER_NEXT_PAD_MS);
  }
}

function warmViaElements(sources: string[]): void {
  for (const src of sources) {
    if (elementWarmCache.has(src)) continue;
    const el = new Audio(src);
    el.preload = "auto";
    try {
      el.load();
    } catch {
      /* ignore */
    }
    elementWarmCache.set(src, el);
  }
}

/**
 * Prefetch every `/audio_lotto/*.wav` via HTMLAudio + Cache API so spin playback
 * is realtime. Does not create blob URLs. Best-effort; respects AbortSignal.
 */
export function warmLottoAudio(options?: { numbers?: boolean }): () => void {
  const abort = new AbortController();
  const sources =
    options?.numbers === false
      ? [
          lottoNamedSrc("start"),
          lottoNamedSrc("first_winner"),
          lottoNamedSrc("second_winner"),
          lottoNamedSrc("third_winner"),
          lottoNamedSrc("next"),
        ]
      : ALL_SOURCES;

  // Immediate HTMLAudio preload (works well in Telegram WebView).
  warmViaElements(sources);

  const timer = window.setTimeout(() => {
    void (async () => {
      let nextIndex = 0;
      const worker = async () => {
        while (!abort.signal.aborted) {
          const index = nextIndex;
          nextIndex += 1;
          if (index >= sources.length) return;
          await cacheAudio(sources[index], abort.signal);
        }
      };
      await Promise.all([worker(), worker(), worker()]);
    })();
  }, 200);

  return () => {
    window.clearTimeout(timer);
    abort.abort();
  };
}

/**
 * Unlock HTMLAudioElement on a user gesture (iOS / Telegram WebView).
 * Safe to call multiple times; restores volume so we never stay silently muted.
 */
export function primeLottoAudioUnlock(): void {
  if (audioUnlocked) {
    ensureAudible();
    return;
  }
  audioUnlocked = true;
  player.muted = false;
  // Gesture unlock at zero volume so lobby taps are not loud; restore ASAP.
  player.volume = 0;
  if (!player.src) player.src = lottoNamedSrc("start");
  void player
    .play()
    .then(() => {
      player.pause();
      player.currentTime = 0;
      player.volume = 1;
    })
    .catch(() => {
      player.volume = 1;
    });
  // Hang-safe: some WebViews leave play() pending; never stay at volume 0.
  window.setTimeout(() => {
    ensureAudible();
  }, 300);
}

/**
 * Unlock HTMLAudioElement on first gesture (iOS / Telegram WebView).
 * Returns a disposer for the listeners.
 */
export function unlockLottoAudio(onUnlocked?: () => void): () => void {
  const unlock = () => {
    primeLottoAudioUnlock();
    onUnlocked?.();
    window.removeEventListener("pointerdown", unlock, true);
    window.removeEventListener("touchstart", unlock, true);
    window.removeEventListener("click", unlock, true);
  };

  window.addEventListener("pointerdown", unlock, { once: true, capture: true });
  window.addEventListener("touchstart", unlock, { once: true, capture: true });
  window.addEventListener("click", unlock, { once: true, capture: true });

  return () => {
    window.removeEventListener("pointerdown", unlock, true);
    window.removeEventListener("touchstart", unlock, true);
    window.removeEventListener("click", unlock, true);
  };
}
