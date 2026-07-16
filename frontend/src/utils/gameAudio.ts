const player = new Audio();
// Let play() initiate the request. Explicit preload + load() caused browsers
// to open an extra byte-range request for the same MP3.
player.preload = "none";

const AUDIO_CACHE_NAME = "bright-games-bingo-audio-v1";
const ALL_AUDIO_SOURCES = [
  ...Array.from({ length: 75 }, (_, index) => `/audios/${index + 1}.mp3`),
  "/audios/bingo.mp3",
  "/audios/beat.mp3",
];

let activeObjectUrl: string | null = null;
let currentLogicalSrc: string | null = null;
let playRequestId = 0;

async function cacheAudio(
  src: string,
  signal?: AbortSignal,
): Promise<Response | null> {
  if (!("caches" in window)) return null;

  try {
    const cache = await caches.open(AUDIO_CACHE_NAME);
    const cached = await cache.match(src);
    if (cached) return cached;

    const response = await fetch(src, { signal });
    const contentType = response.headers.get("content-type") ?? "";

    if (!response.ok || !contentType.startsWith("audio/")) {
      return null;
    }

    await cache.put(src, response.clone());
    return response;
  } catch {
    return null;
  }
}

async function cachedPlayableUrl(src: string): Promise<string> {
  const response = await cacheAudio(src);
  if (!response) return src;

  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

async function warmAudioCache(signal: AbortSignal): Promise<void> {
  // Keep only the two event sounds on data-saver. Number files will still be
  // cached on first use.
  const browserConnection = (
    navigator as Navigator & { connection?: { saveData?: boolean } }
  ).connection;
  const sources = browserConnection?.saveData
    ? [BINGO_AUDIO_SRC, NEW_GAME_AUDIO_SRC]
    : ALL_AUDIO_SOURCES;

  let nextIndex = 0;
  const worker = async () => {
    while (!signal.aborted) {
      const index = nextIndex;
      nextIndex += 1;
      if (index >= sources.length) return;
      await cacheAudio(sources[index], signal);
    }
  };

  // A few sequential workers warm the cache during the lobby without
  // flooding a mobile connection with 77 simultaneous requests.
  await Promise.all([worker(), worker(), worker()]);
}

/**
 * Plays one game sound at a time. Browsers may reject playback before the
 * user's first interaction; that is intentionally treated as best-effort.
 */
export async function playGameAudio(src: string): Promise<boolean> {
  const requestId = ++playRequestId;

  try {
    player.pause();

    if (currentLogicalSrc !== src) {
      const playableSrc = await cachedPlayableUrl(src);

      // A newer call/winner sound superseded this cache read.
      if (requestId !== playRequestId) {
        if (playableSrc.startsWith("blob:")) URL.revokeObjectURL(playableSrc);
        return false;
      }

      if (activeObjectUrl) URL.revokeObjectURL(activeObjectUrl);
      activeObjectUrl = playableSrc.startsWith("blob:") ? playableSrc : null;
      currentLogicalSrc = src;
      player.src = playableSrc;
    }

    player.currentTime = 0;
    await player.play();
    return true;
  } catch {
    // Telegram/browser autoplay policy may block sound before first tap.
    return false;
  }
}

/** Explicit user-gesture retry used after a browser blocks autoplay. */
export async function enableGameAudio(): Promise<boolean> {
  try {
    player.muted = false;
    player.currentTime = 0;
    await player.play();
    return true;
  } catch {
    return false;
  }
}

export function stopGameAudio(): void {
  playRequestId += 1;
  player.pause();
  player.currentTime = 0;
}

export function numberAudioSrc(number: number): string {
  return `/audios/${number}.mp3`;
}

export const BINGO_AUDIO_SRC = "/audios/bingo.mp3";
export const NEW_GAME_AUDIO_SRC = "/audios/beat.mp3";

/**
 * Unlock the shared audio element on the first user gesture. Reusing one
 * element is important on iOS/Telegram, where creating a new element for
 * every called number can be blocked by autoplay policy.
 */
export function preloadEventSounds(onUnlocked?: () => void): () => void {
  const cacheAbortController = new AbortController();
  const warmTimer = window.setTimeout(() => {
    void warmAudioCache(cacheAbortController.signal);
  }, 1200);

  const unlock = () => {
    // If a call already tried to play after a refresh, resume that exact
    // audio inside this user gesture instead of replacing it with the beat.
    if (currentLogicalSrc) {
      player.muted = false;
      player.currentTime = 0;
      void player
        .play()
        .then(() => onUnlocked?.())
        .catch(() => undefined);

      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("touchstart", unlock);
      return;
    }

    player.src = NEW_GAME_AUDIO_SRC;
    currentLogicalSrc = null;
    // Start an unmuted media element inside the gesture, but at zero volume.
    // This unlocks future audible calls more reliably than muted autoplay in
    // iOS/Telegram WebViews without making the beat audible in the lobby.
    player.muted = false;
    player.volume = 0;
    void player
      .play()
      .then(() => {
        player.pause();
        player.currentTime = 0;
        player.volume = 1;
        onUnlocked?.();
      })
      .catch(() => {
        player.volume = 1;
      });

    window.removeEventListener("pointerdown", unlock);
    window.removeEventListener("touchstart", unlock);
  };

  window.addEventListener("pointerdown", unlock, { once: true });
  window.addEventListener("touchstart", unlock, { once: true });

  return () => {
    window.clearTimeout(warmTimer);
    cacheAbortController.abort();
    window.removeEventListener("pointerdown", unlock);
    window.removeEventListener("touchstart", unlock);
  };
}
