import { useEffect, useState } from "react";
import { LogOut, User } from "lucide-react";
import { getMe, getMyTransactions, updateBalance } from "../services/api";

type TransactionType = {
  type: "deposit" | "withdraw";
  amount: number;
  reason: string;
  created_at: string;
};

type UserType = {
  id: string; // required for admin updates
  email: string | null; // can be null for Telegram users
  telegram_username: string | null;
  telegram_first_name?: string | null;
  is_admin: boolean;
  balance: number;
};

const Me = () => {
  const [user, setUser] = useState<UserType | null>(null);
  const [transactions, setTransactions] = useState<TransactionType[]>([]);
  const [loading, setLoading] = useState(true);
  const [amount, setAmount] = useState<number>(0);
  const [reason, setReason] = useState("");
  const token = localStorage.getItem("token");

  const handleLogout = () => {
    localStorage.removeItem("token");
    window.location.reload();
  };

  const fetchData = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const userData = await getMe(token);
      setUser(userData);

      if (!userData.is_admin) {
        const txns = await getMyTransactions();
        setTransactions(txns);
      }
    } catch (err) {
      console.error(err);
      handleLogout();
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleUpdateBalance = async () => {
    if (!user || !token) return;
    if (!amount || !reason) return alert("Enter amount and reason");

    try {
      await updateBalance(token, {
        user_id: user.id, // 🔥 Use UUID for all users (email optional)
        amount,
        note: reason, // optional note for backend
      });
      setAmount(0);
      setReason("");
      alert("Balance updated successfully!");
      fetchData();
    } catch (err: any) {
      alert(err.message || "Failed to update balance");
    }
  };

  return (
    <div className="p-4 space-y-4">
      {/* Profile card */}
      <div className="rounded-2xl bg-zinc-900 border border-zinc-800 p-4 flex items-center gap-4">
        <div className="h-12 w-12 rounded-full bg-emerald-600 flex items-center justify-center">
          <User className="text-black" />
        </div>
        <div>
          <p className="font-semibold text-white">
            {loading
              ? "Loading..."
              : user?.email || user?.telegram_username || "Unknown User"}
          </p>
          <p className="text-sm text-zinc-400">
            {loading ? "" : `Balance: $${user?.balance.toFixed(2)}`}
          </p>
        </div>
      </div>

      {/* Admin: deposit/withdraw form */}
      {user?.is_admin && (
        <div className="space-y-2">
          <h2 className="font-bold text-white">Admin: Update Balance</h2>
          <input
            type="number"
            value={amount}
            onChange={(e) => setAmount(parseFloat(e.target.value))}
            placeholder="Amount"
            className="w-full rounded-xl bg-zinc-800 px-4 py-2 text-white border border-zinc-700"
          />
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Reason"
            className="w-full rounded-xl bg-zinc-800 px-4 py-2 text-white border border-zinc-700"
          />
          <button
            onClick={handleUpdateBalance}
            className="w-full bg-emerald-600 py-2 rounded-xl text-white font-semibold hover:bg-emerald-700 transition"
          >
            Update Balance
          </button>
        </div>
      )}

      {/* Normal users: transactions table */}
      {!user?.is_admin && (
        <div className="mt-4">
          <h2 className="font-bold text-white mb-2">Transactions</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-white border border-zinc-700">
              <thead>
                <tr className="bg-zinc-800">
                  <th className="px-2 py-1">Type</th>
                  <th className="px-2 py-1">Amount</th>
                  <th className="px-2 py-1">Reason</th>
                  <th className="px-2 py-1">Date</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((t, idx) => (
                  <tr
                    key={idx}
                    className="border-t border-zinc-700 even:bg-zinc-900/50"
                  >
                    <td className="px-2 py-1">{t.type}</td>
                    <td className="px-2 py-1">{t.amount.toFixed(2)}</td>
                    <td className="px-2 py-1">{t.reason}</td>
                    <td className="px-2 py-1">
                      {new Date(t.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Logout */}
      <button
        onClick={handleLogout}
        className="w-full flex items-center justify-center gap-2 rounded-xl border border-red-500/40 text-red-400 py-3 hover:bg-red-500/10 transition"
      >
        <LogOut size={18} />
        Logout
      </button>
    </div>
  );
};

export default Me;
