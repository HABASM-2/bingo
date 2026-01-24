import { useEffect, useState } from "react";
import { LogOut, User } from "lucide-react";
import {
  getMe,
  getMyTransactions,
  updateBalance,
  requestWithdraw,
  cancelWithdraw,
  getAllWithdraws,
  updateWithdrawStatus,
} from "../services/api";

type TransactionType = {
  id: string;
  type: "deposit" | "withdraw";
  amount: number;
  reason: string;
  created_at: string;
  withdraw_status?:
    | "pending"
    | "processing"
    | "completed"
    | "rejected"
    | "cancelled";
};

type UserType = {
  id: string;
  email: string | null;
  telegram_username: string | null;
  telegram_first_name?: string | null;
  is_admin: boolean;
  balance: number;
};

type WithdrawAdminType = {
  id: string;
  username: string;
  first_name: string;
  user_id: string;
  amount: number;
  bank?: string;
  account_number?: string;
  status: "pending" | "processing" | "completed" | "rejected" | "cancelled";
  date: string;
};

const Me = () => {
  const [user, setUser] = useState<UserType | null>(null);
  const [transactions, setTransactions] = useState<TransactionType[]>([]);
  const [withdraws, setWithdraws] = useState<WithdrawAdminType[]>([]);
  const [loading, setLoading] = useState(true);

  // Pagination
  const [page, setPage] = useState(0);
  const [pageSize] = useState(10);
  const [totalWithdraws, setTotalWithdraws] = useState(0);

  // Admin balance controls
  const [amount, setAmount] = useState<number>(0);
  const [reason, setReason] = useState("");

  // User withdraw controls
  const [withdrawAmount, setWithdrawAmount] = useState<number>(0);
  const [withdrawNote, setWithdrawNote] = useState("");

  // Loading for user actions
  const [withdrawLoading, setWithdrawLoading] = useState(false);
  const [cancelLoadingId, setCancelLoadingId] = useState<string | null>(null);

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
        const txns = await getMyTransactions(); // includes withdraw_status
        setTransactions(txns);
      } else {
        const res = await getAllWithdraws(token, page, pageSize);
        setWithdraws(res.withdraws);
        setTotalWithdraws(res.total);
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
  }, [page]);

  // 🛡 Admin update balance
  const handleUpdateBalance = async () => {
    if (!user || !token) return;
    if (!amount || !reason) return alert("Enter amount and reason");

    try {
      await updateBalance(token, {
        user_id: user.id,
        amount,
        note: reason,
      });
      setAmount(0);
      setReason("");
      alert("Balance updated!");
      fetchData();
    } catch (err: any) {
      alert(err.message || "Failed");
    }
  };

  // 💸 User withdraw request
  const handleWithdraw = async () => {
    if (!user) return;

    if (!withdrawAmount || withdrawAmount <= 0) {
      return alert("Enter a valid amount");
    }

    if (withdrawAmount > user.balance) {
      return alert(
        `Insufficient balance. Your balance is $${user.balance.toFixed(2)}`,
      );
    }

    try {
      setWithdrawLoading(true); // 🔄 Start loading
      await requestWithdraw(token!, withdrawAmount, withdrawNote);
      alert("Withdraw request submitted successfully!");

      setWithdrawAmount(0);
      setWithdrawNote("");
      await fetchData(); // 🔄 Refresh transactions and balance
    } catch (err: any) {
      const msg =
        err.response?.data?.detail || err.message || "Withdraw request failed";
      alert(msg);
    } finally {
      setWithdrawLoading(false); // 🔄 Stop loading
    }
  };

  // ❌ Cancel withdraw
  const handleCancel = async (txId: string) => {
    try {
      setCancelLoadingId(txId); // 🔄 Start loading for this transaction
      await cancelWithdraw(token!, txId);
      alert("Withdraw cancelled successfully!");
      await fetchData(); // 🔄 Refresh transactions
    } catch (err: any) {
      const msg =
        err.response?.data?.detail ||
        err.message ||
        "Failed to cancel withdraw";
      alert(msg);
    } finally {
      setCancelLoadingId(null); // 🔄 Stop loading
    }
  };

  // ⚡ Admin change withdraw status
  const handleAdminUpdate = async (id: string, status: string) => {
    try {
      await updateWithdrawStatus(token!, id, status);
      fetchData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  return (
    <div className="p-4 space-y-4 min-h-screen">
      {/* Profile */}
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

      {/* 👑 Admin Controls */}
      {user?.is_admin && (
        <div className="space-y-4">
          {/* Admin: Update Balance */}
          <div className="space-y-2 bg-zinc-900 p-4 rounded-2xl border border-zinc-800">
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
              className="w-full bg-emerald-600 py-2 rounded-xl text-white font-semibold"
            >
              Update Balance
            </button>
          </div>

          {/* Admin Withdraw Management */}
          <div className="space-y-2">
            <h2 className="font-bold text-white text-lg">Withdraw Requests</h2>
            {loading && <p>Loading...</p>}
            {!loading && withdraws.length === 0 && (
              <p className="text-zinc-400">No withdraw requests</p>
            )}

            <div className="overflow-x-auto max-w-full border border-zinc-700 rounded-xl">
              <table className="min-w-[800px] border-collapse border border-zinc-700 text-white">
                <thead>
                  <tr className="bg-zinc-800">
                    <th className="px-2 py-1 sticky top-0 left-0 bg-zinc-800 z-30 text-left">
                      User
                    </th>
                    <th className="px-2 py-1 sticky top-0 bg-zinc-800 z-20 text-left">
                      Amount
                    </th>
                    <th className="px-2 py-1 sticky top-0 bg-zinc-800 z-20 text-left">
                      Bank
                    </th>
                    <th className="px-2 py-1 sticky top-0 bg-zinc-800 z-20 text-left">
                      Account
                    </th>
                    <th className="px-2 py-1 sticky top-0 bg-zinc-800 z-20 text-left">
                      Date
                    </th>
                    <th className="px-2 py-1 sticky top-0 bg-zinc-800 z-20 text-left">
                      Status
                    </th>
                    <th className="px-2 py-1 sticky top-0 bg-zinc-800 z-20 text-left">
                      Action
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {withdraws.map((w) => (
                    <tr
                      key={w.id}
                      className="border-t border-zinc-700 hover:bg-zinc-900"
                    >
                      <td className="px-2 py-1 sticky left-0 bg-zinc-900 z-20">
                        {w.username || w.first_name || "Player"}
                      </td>
                      <td className="px-2 py-1">${w.amount.toFixed(2)}</td>
                      <td className="px-2 py-1">{w.bank || "-"}</td>
                      <td className="px-2 py-1">{w.account_number || "-"}</td>
                      <td className="px-2 py-1">
                        {new Date(w.date).toLocaleString()}
                      </td>
                      <td className="px-2 py-1">
                        <span
                          className={`px-2 py-1 rounded-full text-xs font-semibold ${
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
                      </td>
                      <td className="px-2 py-1 flex gap-2">
                        {w.status === "pending" && (
                          <>
                            <button
                              onClick={() =>
                                handleAdminUpdate(w.id, "processing")
                              }
                              className="bg-blue-600 px-3 py-1 rounded-lg text-sm"
                            >
                              Process
                            </button>
                            <button
                              onClick={() =>
                                handleAdminUpdate(w.id, "rejected")
                              }
                              className="bg-red-600 px-3 py-1 rounded-lg text-sm"
                            >
                              Reject
                            </button>
                          </>
                        )}
                        {w.status === "processing" && (
                          <button
                            onClick={() => handleAdminUpdate(w.id, "completed")}
                            className="bg-green-600 px-3 py-1 rounded-lg text-sm"
                          >
                            Mark Paid
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls - OUTSIDE the scrollable div */}
            <div className="flex justify-between items-center mt-2 px-2">
              <button
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
                className="px-3 py-1 bg-zinc-800 rounded-xl text-white disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <span className="text-sm text-zinc-400">
                Page {page + 1} of {Math.ceil(totalWithdraws / pageSize)}
              </span>
              <button
                disabled={(page + 1) * pageSize >= totalWithdraws}
                onClick={() => setPage(page + 1)}
                className="px-3 py-1 bg-zinc-800 rounded-xl text-white disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 💸 User Withdraw Request */}
      {!user?.is_admin && (
        <div className="bg-zinc-900 p-4 rounded-2xl border border-zinc-800 space-y-2">
          <h2 className="font-bold">Request Withdraw</h2>
          <input
            type="number"
            placeholder="Amount"
            value={withdrawAmount}
            onChange={(e) => setWithdrawAmount(parseFloat(e.target.value))}
            className="w-full bg-zinc-800 p-2 rounded-xl"
          />
          <input
            type="text"
            placeholder="Payment details (optional)"
            value={withdrawNote}
            onChange={(e) => setWithdrawNote(e.target.value)}
            className="w-full bg-zinc-800 p-2 rounded-xl"
          />
          <button
            onClick={handleWithdraw}
            className={`w-full bg-red-600 py-2 rounded-xl font-semibold ${
              withdrawLoading ? "opacity-50 cursor-not-allowed" : ""
            }`}
            disabled={withdrawLoading}
          >
            {withdrawLoading ? "Processing..." : "Withdraw"}
          </button>
        </div>
      )}

      {/* 📜 Transactions (user only) */}
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
                  <th className="px-2 py-1">Status</th>
                  <th className="px-2 py-1">Action</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((t) => (
                  <tr key={t.id} className="border-t border-zinc-700">
                    <td className="px-2 py-1">{t.type}</td>
                    <td className="px-2 py-1">${t.amount.toFixed(2)}</td>
                    <td className="px-2 py-1">{t.reason}</td>
                    <td className="px-2 py-1">
                      {new Date(t.created_at).toLocaleString()}
                    </td>
                    <td className="px-2 py-1">
                      {t.type === "withdraw" && (
                        <span
                          className={`text-xs px-2 py-1 rounded-full font-semibold ${
                            t.withdraw_status === "pending"
                              ? "bg-yellow-500/20 text-yellow-400"
                              : t.withdraw_status === "processing"
                                ? "bg-blue-500/20 text-blue-400"
                                : t.withdraw_status === "completed"
                                  ? "bg-green-500/20 text-green-400"
                                  : t.withdraw_status === "cancelled"
                                    ? "bg-red-500/20 text-red-400"
                                    : ""
                          }`}
                        >
                          {t.withdraw_status === "completed"
                            ? "Paid"
                            : t.withdraw_status || "pending"}
                        </span>
                      )}
                    </td>
                    <td className="px-2 py-1">
                      {t.type === "withdraw" &&
                        t.withdraw_status === "pending" && (
                          <button
                            onClick={() => handleCancel(t.id)}
                            className={`text-red-400 underline text-sm ${
                              cancelLoadingId === t.id
                                ? "opacity-50 cursor-not-allowed"
                                : ""
                            }`}
                            disabled={cancelLoadingId === t.id}
                          >
                            {cancelLoadingId === t.id
                              ? "Cancelling..."
                              : "Cancel"}
                          </button>
                        )}
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
