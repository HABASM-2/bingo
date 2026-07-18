import type { NavTab } from "../components/bingo/BottomNav";
import {
  isLaunchGame,
  launchGameToTab,
  readTelegramLaunch,
} from "./telegramLaunch";

/** sessionStorage key for the last active bottom-nav tab. */
export const NAV_TAB_STORAGE_KEY = "brightgames:navTab";

const NAV_TABS: readonly NavTab[] = [
  "home",
  "bingo",
  "dama",
  "aviator",
  "plinko",
  "lotto",
  "profile",
  "admin",
] as const;

export function isNavTab(value: unknown): value is NavTab {
  return typeof value === "string" && (NAV_TABS as readonly string[]).includes(value);
}

export function readSavedNavTab(): NavTab | null {
  if (typeof sessionStorage === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(NAV_TAB_STORAGE_KEY);
    return isNavTab(raw) ? raw : null;
  } catch {
    return null;
  }
}

export function writeSavedNavTab(tab: NavTab): void {
  if (typeof sessionStorage === "undefined") return;
  try {
    sessionStorage.setItem(NAV_TAB_STORAGE_KEY, tab);
  } catch {
    /* private mode / quota — ignore */
  }
}

export type InitialNavResolution = {
  tab: NavTab;
  /** Deep-link asked for admin; wait for `/admin/me` before switching. */
  adminDeepLinkPending: boolean;
  /** Saved tab was admin; restore only after capability check. */
  adminRestorePending: boolean;
};

/**
 * Resolve the tab to show on first paint.
 * Priority: one-time deep-link (`?game=` / start_param) → sessionStorage → home.
 * Admin is never restored until the server confirms capability.
 */
export function resolveInitialNavTab(
  launch: { game: string | null } = readTelegramLaunch(),
  saved: NavTab | null = readSavedNavTab(),
): InitialNavResolution {
  if (launch.game === "admin") {
    return { tab: "home", adminDeepLinkPending: true, adminRestorePending: false };
  }
  if (isLaunchGame(launch.game)) {
    return {
      tab: launchGameToTab(launch.game),
      adminDeepLinkPending: false,
      adminRestorePending: false,
    };
  }
  if (saved === "admin") {
    return { tab: "home", adminDeepLinkPending: false, adminRestorePending: true };
  }
  if (saved) {
    return { tab: saved, adminDeepLinkPending: false, adminRestorePending: false };
  }
  return { tab: "home", adminDeepLinkPending: false, adminRestorePending: false };
}
