import { useEffect, useState } from "react";

// ---------------------------
// TypeScript Interfaces
// ---------------------------
interface LeaderboardEntry {
  game_no: string;
  winner: string;
  amount: number; // amount won
  stake_amount: number; // stake used
}

interface BetEntry {
  game_no: string;
  selected_number?: number | null;
  winning_number?: number | null;
  stake_amount: number;
  result_amount?: number; // profit or 0
  status: "won" | "lost" | "cancelled";
  created_at?: string;
}

// ---------------------------
// History Component
// ---------------------------
const History: React.FC = () => {
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [bets, setBets] = useState<BetEntry[]>([]);
  const validBets = bets.filter(
    (b) => b.game_no && b.game_no.toString().trim() !== "",
  );

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const res = await fetch("/bingo/history", {
          headers: {
            Authorization: "Bearer " + localStorage.getItem("token"),
          },
        });
        const data = await res.json();

        if (!data.error) {
          setLeaderboard(data.leaderboard || []);
          setBets(data.bets || []);
        }
      } catch (err) {
        console.error("Failed to fetch history:", err);
      }
    };

    fetchHistory();
  }, []);

  return (
    <div className="p-4 text-white">
      {/* --------------------------- */}
      {/* Leaderboard */}
      {/* --------------------------- */}
      <h1 className="text-xl font-bold text-emerald-400">
        Leaderboard (Last 5 Winners)
      </h1>
      <div className="mt-2 space-y-2">
        {leaderboard.length === 0 ? (
          <p>No winners yet</p>
        ) : (
          leaderboard.map((l, i) => (
            <div
              key={i}
              className="flex justify-between bg-zinc-800 p-2 rounded items-center"
            >
              <span className="font-semibold">{l.winner}</span>
              <span>Game #{l.game_no}</span>
              <span>Stake: ${l.stake_amount.toFixed(2)}</span>
              <span>Won: ${l.amount.toFixed(2)}</span>
            </div>
          ))
        )}
      </div>

      {/* --------------------------- */}
      {/* User Bet History */}
      {/* --------------------------- */}
      <h1 className="text-xl font-bold text-emerald-400 mt-6">
        Your Game History
      </h1>

      <div className="mt-3 space-y-3">
        {validBets.length === 0 ? (
          <p>No games played yet</p>
        ) : (
          validBets.map((b, i) => (
            <div
              key={i}
              className="bg-zinc-800 p-3 rounded-lg shadow flex flex-col gap-1"
            >
              {/* Top row */}
              <div className="flex justify-between items-center">
                <span className="font-semibold text-emerald-400">
                  🎮 Game #{b.game_no}
                </span>
                <span
                  className={`font-bold ${
                    b.status === "won"
                      ? "text-green-400"
                      : b.status === "lost"
                        ? "text-red-400"
                        : "text-yellow-400"
                  }`}
                >
                  {b.status.toUpperCase()}
                </span>
              </div>

              {/* Numbers */}
              <div className="flex justify-between text-sm">
                <span>🎯 Your Number: {b.selected_number ?? "-"}</span>
                <span>🎲 Winning Number: {b.winning_number ?? "-"}</span>
              </div>

              {/* Money */}
              <div className="flex justify-between text-sm">
                <span>💰 Stake: ${b.stake_amount.toFixed(2)}</span>
                <span>
                  🏆 Result:{" "}
                  {b.status === "won"
                    ? `+${b.result_amount?.toFixed(2) ?? "0.00"}`
                    : b.status === "lost"
                      ? `-${b.stake_amount.toFixed(2)}`
                      : "0.00"}
                </span>
              </div>

              {/* Date */}
              {b.created_at && (
                <div className="text-xs text-gray-400 text-right">
                  {new Date(b.created_at).toLocaleString()}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default History;
