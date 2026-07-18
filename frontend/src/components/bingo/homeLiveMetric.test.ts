/**
 * Home live-now metric = taken boards while lobby/in_progress.
 * Run: npx tsx src/components/bingo/homeLiveMetric.test.ts
 */
import { bingoHomeLiveBoardCount } from "./homeLiveMetric";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

assert(
  bingoHomeLiveBoardCount("lobby", [1, 2, 3]) === 3,
  "lobby uses taken board count",
);
assert(
  bingoHomeLiveBoardCount("in_progress", [4, 5]) === 2,
  "in_progress uses taken board count",
);
assert(
  bingoHomeLiveBoardCount("lobby", []) === 0,
  "empty lobby selection is zero",
);
assert(
  bingoHomeLiveBoardCount("finished", [1, 2, 3]) === null,
  "finished hides live count",
);
assert(
  bingoHomeLiveBoardCount(null, [1]) === null,
  "unknown status hides live count",
);
assert(
  bingoHomeLiveBoardCount("lobby", null) === 0,
  "missing taken boards treated as empty",
);

console.log("homeLiveMetric tests OK");
