/**
 * Nav tab persistence + deep-link precedence.
 * Run: npx tsx src/utils/navTabStorage.test.ts
 */
import {
  isNavTab,
  resolveInitialNavTab,
  NAV_TAB_STORAGE_KEY,
} from "./navTabStorage";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

assert(isNavTab("bingo"), "bingo is a valid tab");
assert(isNavTab("home"), "home is a valid tab");
assert(!isNavTab("settings"), "settings is not a nav tab");
assert(!isNavTab(null), "null is not a nav tab");

assert(
  NAV_TAB_STORAGE_KEY === "brightgames:navTab",
  "storage key must stay namespaced",
);

{
  const r = resolveInitialNavTab({ game: "bingo" }, "home");
  assert(r.tab === "bingo", "deep-link bingo overrides saved home");
  assert(!r.adminDeepLinkPending && !r.adminRestorePending, "no admin pending");
}

{
  const r = resolveInitialNavTab({ game: "dama" }, "bingo");
  assert(r.tab === "dama", "deep-link dama overrides saved bingo");
}

{
  const r = resolveInitialNavTab({ game: null }, "bingo");
  assert(r.tab === "bingo", "saved bingo restores without deep-link");
}

{
  const r = resolveInitialNavTab({ game: null }, "admin");
  assert(r.tab === "home", "saved admin does not restore until capability check");
  assert(r.adminRestorePending, "admin restore pending");
}

{
  const r = resolveInitialNavTab({ game: "admin" }, "bingo");
  assert(r.tab === "home", "admin deep-link stays on home until capability");
  assert(r.adminDeepLinkPending, "admin deep-link pending");
}

{
  const r = resolveInitialNavTab({ game: null }, null);
  assert(r.tab === "home", "default is home");
}

console.log("navTabStorage tests OK");
