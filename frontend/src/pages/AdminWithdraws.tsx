import { useEffect, useState } from "react";
import { getAllWithdraws, updateWithdrawStatus } from "../services/api";

type Withdraw = {
  id: string;
  user_id: string;
  amount: number;
  status: "pending" | "processing" | "completed" | "rejected" | "cancelled";
  date: string;
};

export default function AdminWithdraws() {
  const [withdraws, setWithdraws] = useState<Withdraw[]>([]);
  const [loading, setLoading] = useState(true);
  const token = localStorage.getItem("token");

  const fetchWithdraws = async () => {
    try {
      const data = await getAllWithdraws(token!);
      setWithdraws(data);
    } catch (err) {
      console.error(err);
      alert("Failed to load withdraws");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWithdraws();
  }, []);

  const handleUpdate = async (id: string, status: string) => {
    try {
      await updateWithdrawStatus(token!, id, status);
      fetchWithdraws();
    } catch (err: any) {
      alert(err.message);
    }
  };

  return (
    <div className="p-4 text-white space-y-4">
      <h1 className="text-2xl font-bold">Withdraw Management</h1>

      {loading && <p>Loading...</p>}

      {!loading && withdraws.length === 0 && (
        <p className="text-zinc-400">No withdraw requests</p>
      )}

      {withdraws.map((w) => (
        <div
          key={w.id}
          className="bg-zinc-900 border border-zinc-800 p-4 rounded-2xl"
        >
          <div className="flex justify-between items-center">
            <div>
              <p className="text-sm text-zinc-400">User ID</p>
              <p className="font-mono text-xs">{w.user_id}</p>
            </div>

            <div className="text-right">
              <p className="text-lg font-bold">${w.amount.toFixed(2)}</p>
              <p className="text-xs text-zinc-400">
                {new Date(w.date).toLocaleString()}
              </p>
            </div>
          </div>

          <div className="mt-3 flex items-center justify-between">
            <span
              className={`px-3 py-1 rounded-full text-xs font-semibold ${
                w.status === "pending"
                  ? "bg-yellow-500/20 text-yellow-400"
                  : w.status === "processing"
                    ? "bg-blue-500/20 text-blue-400"
                    : w.status === "completed"
                      ? "bg-green-500/20 text-green-400"
                      : "bg-red-500/20 text-red-400"
              }`}
            >
              {w.status}
            </span>

            {/* ACTION BUTTONS */}
            <div className="flex gap-2">
              {w.status === "pending" && (
                <>
                  <button
                    onClick={() => handleUpdate(w.id, "processing")}
                    className="bg-blue-600 px-3 py-1 rounded-lg text-sm"
                  >
                    Start Processing
                  </button>
                  <button
                    onClick={() => handleUpdate(w.id, "rejected")}
                    className="bg-red-600 px-3 py-1 rounded-lg text-sm"
                  >
                    Reject
                  </button>
                </>
              )}

              {w.status === "processing" && (
                <button
                  onClick={() => handleUpdate(w.id, "completed")}
                  className="bg-green-600 px-3 py-1 rounded-lg text-sm"
                >
                  Mark Paid
                </button>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
