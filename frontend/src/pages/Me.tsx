import { useEffect, useState } from "react";
import { User } from "lucide-react";
import {
  getMe,
  getMyTransactions,
  getAllWithdraws,
  updateWithdrawStatus,
} from "../services/api";

// Each period now tracks both deposits (per provider) and withdraws (per bank)
export type FinancialOverviewPeriod = {
  deposits: { [provider: string]: number }; // e.g., Telebirr, CBE, Abyssinia
  total_deposits: number;
  withdraws: { [bank: string]: number }; // e.g., Telebirr, CBE, Abyssinia
  total_withdraws: number;
  total_users_holding: number; // total user balances
  profit: number; // total_deposits - total_withdraws - total_holding
};

// Complete overview for all durations
export type FinancialOverview = {
  today: FinancialOverviewPeriod;
  week: FinancialOverviewPeriod;
  month: FinancialOverviewPeriod;
  year: FinancialOverviewPeriod;
};

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
  const [_totalWithdraws, setTotalWithdraws] = useState(0);
  const token = localStorage.getItem("token");
  const [actionLoading, setActionLoading] = useState<{
    [id: string]: string | null;
  }>({});

  const [selectedPeriod, setSelectedPeriod] = useState<
    "today" | "week" | "month" | "year"
  >("today");

  const [financialOverview, setFinancialOverview] =
    useState<FinancialOverview | null>(null);

  const validWithdraws = withdraws.filter(
    (w) =>
      w.bank &&
      w.bank.trim() !== "" &&
      w.account_number &&
      w.account_number.trim() !== "",
  );

  const fetchFinancialOverview = async () => {
    if (!token) return;
    try {
      const res = await fetch("/admin/financial-overview", {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      setFinancialOverview(data);
    } catch (err) {
      console.error("Failed to fetch financial overview:", err);
    }
  };

  useEffect(() => {
    const init = async () => {
      await fetchData(); // fetch user first
    };
    init();
  }, []); // run once on mount

  // Fetch financial overview after user is loaded and is admin
  useEffect(() => {
    if (user?.is_admin) {
      fetchFinancialOverview();
    }
  }, [user?.is_admin]);

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

  // ⚡ Admin change withdraw status
  const handleAdminUpdate = async (id: string, status: string) => {
    try {
      setActionLoading((prev) => ({ ...prev, [id]: status })); // start loading
      await updateWithdrawStatus(token!, id, status);
      fetchData(); // refresh data after action
    } catch (err: any) {
      alert(err.message);
    } finally {
      setActionLoading((prev) => ({ ...prev, [id]: null })); // stop loading
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
            {loading
              ? ""
              : user?.is_admin && financialOverview
                ? `Profit: $${financialOverview[selectedPeriod].profit.toFixed(2)}`
                : `Balance: $${user?.balance.toFixed(2)}`}
          </p>
        </div>
      </div>

      {user?.is_admin && financialOverview && (
        <div className="space-y-4">
          <h2 className="font-bold text-white text-lg">Financial Overview</h2>

          {/* Period selector */}
          <div className="flex gap-2 mb-2">
            {(["today", "week", "month", "year"] as const).map((period) => (
              <button
                key={period}
                onClick={() => setSelectedPeriod(period)}
                className={`px-3 py-1 rounded-xl font-semibold ${
                  selectedPeriod === period
                    ? "bg-emerald-600 text-black"
                    : "bg-zinc-800 text-white"
                }`}
              >
                {period.charAt(0).toUpperCase() + period.slice(1)}
              </button>
            ))}
          </div>

          {/* Display single smart card */}
          <div className="bg-zinc-900 p-4 rounded-2xl border border-zinc-800 text-white">
            {(() => {
              const data = financialOverview[selectedPeriod];
              return (
                <>
                  <h3 className="font-semibold capitalize mb-2">
                    {selectedPeriod}
                  </h3>

                  {/* Deposits */}
                  <p className="text-sm text-zinc-400">Deposits:</p>
                  {Object.keys(data.deposits).length ? (
                    <ul className="ml-2 text-sm">
                      {Object.entries(data.deposits).map(
                        ([provider, amount]) => (
                          <li key={provider}>
                            {provider}: ${amount.toFixed(2)}
                          </li>
                        ),
                      )}
                    </ul>
                  ) : (
                    <p className="ml-2 text-sm text-zinc-500">No deposits</p>
                  )}
                  <p className="mt-1 text-sm">
                    <strong>Total Deposits:</strong> $
                    {data.total_deposits.toFixed(2)}
                  </p>

                  {/* Withdraws */}
                  <p className="mt-2 text-sm text-zinc-400">Withdraws:</p>
                  {Object.keys(data.withdraws).length ? (
                    <ul className="ml-2 text-sm">
                      {Object.entries(data.withdraws).map(([bank, amount]) => (
                        <li key={bank}>
                          {bank || "Unknown"}: ${amount.toFixed(2)}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="ml-2 text-sm text-zinc-500">No withdrawals</p>
                  )}
                  <p className="text-sm">
                    <strong>Total Withdraws:</strong> $
                    {data.total_withdraws.toFixed(2)}
                  </p>

                  {/* User Holdings */}
                  <p className="text-sm">
                    <strong>Total Users Holding:</strong> $
                    {data.total_users_holding.toFixed(2)}
                  </p>

                  {/* Profit */}
                  <p className="mt-2 font-semibold">
                    Profit: ${data.profit.toFixed(2)}
                  </p>
                </>
              );
            })()}
          </div>
        </div>
      )}

      {/* 👑 Admin Controls */}
      {user?.is_admin && (
        <div className="space-y-4">
          {/* Admin Withdraw Management */}
          <div className="space-y-2">
            <h2 className="font-bold text-white text-lg">Withdraw Requests</h2>
            {loading && <p>Loading...</p>}
            {!loading && withdraws.length === 0 && (
              <p className="text-zinc-400">No withdraw requests</p>
            )}

            <div className="overflow-x-auto border border-zinc-700 rounded-xl">
              <table className="min-w-[800px] border-collapse border border-zinc-700 text-white">
                <thead>
                  <tr>
                    <th
                      className="px-2 py-1 sticky top-0 left-0 bg-zinc-800 z-40 text-left"
                      style={{ minWidth: "120px", width: "120px" }} // <-- set width
                    >
                      User
                    </th>
                    <th
                      className="px-2 py-1 sticky top-0 left-[120px] bg-zinc-800 z-40 text-left"
                      style={{ minWidth: "100px", width: "100px" }} // <-- set width
                    >
                      Amount
                    </th>
                    <th className="px-2 py-1 sticky top-0 bg-zinc-800 z-30 text-left">
                      Bank
                    </th>
                    <th className="px-2 py-1 sticky top-0 bg-zinc-800 z-30 text-left">
                      Account
                    </th>
                    <th className="px-2 py-1 sticky top-0 bg-zinc-800 z-30 text-left">
                      Date
                    </th>
                    <th className="px-2 py-1 sticky top-0 bg-zinc-800 z-30 text-left">
                      Status
                    </th>
                    <th className="px-2 py-1 sticky top-0 bg-zinc-800 z-30 text-left">
                      Action
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {validWithdraws
                    .slice(page * pageSize, (page + 1) * pageSize)
                    .map((w) => (
                      <tr
                        key={w.id}
                        className="border-t border-zinc-700 hover:bg-zinc-900"
                      >
                        <td
                          className="px-2 py-1 sticky left-0 bg-zinc-900 z-20"
                          style={{ minWidth: "120px", width: "120px" }} // <-- match header width
                        >
                          {w.username || w.first_name || "Player"}
                        </td>
                        <td
                          className="px-2 py-1 sticky left-[120px] bg-zinc-900 z-20"
                          style={{ minWidth: "100px", width: "100px" }} // <-- match header width
                        >
                          ${w.amount.toFixed(2)}
                        </td>
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
                        <td className="px-2 py-1 flex gap-1">
                          {w.status === "pending" && (
                            <>
                              <button
                                onClick={() =>
                                  handleAdminUpdate(w.id, "processing")
                                }
                                className="bg-blue-600 px-2 py-0.5 rounded-md text-xs"
                                disabled={!!actionLoading[w.id]}
                              >
                                {actionLoading[w.id] === "processing"
                                  ? "Processing..."
                                  : "Process"}
                              </button>
                              <button
                                onClick={() =>
                                  handleAdminUpdate(w.id, "rejected")
                                }
                                className="bg-red-600 px-2 py-0.5 rounded-md text-xs"
                                disabled={!!actionLoading[w.id]}
                              >
                                {actionLoading[w.id] === "rejected"
                                  ? "Rejecting..."
                                  : "Reject"}
                              </button>
                            </>
                          )}
                          {w.status === "processing" && (
                            <button
                              onClick={() =>
                                handleAdminUpdate(w.id, "completed")
                              }
                              className="bg-green-600 px-2 py-0.5 rounded-md text-xs"
                              disabled={!!actionLoading[w.id]}
                            >
                              {actionLoading[w.id] === "completed"
                                ? "Marking Paid..."
                                : "Mark Paid"}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            <div className="flex justify-between items-center mt-2 px-2">
              <button
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
                className="px-3 py-1 bg-zinc-800 rounded-xl text-white disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <span className="text-sm text-zinc-400">
                Page {page + 1} of {Math.ceil(withdraws.length / pageSize)}
              </span>
              <button
                disabled={(page + 1) * pageSize >= withdraws.length}
                onClick={() => setPage(page + 1)}
                className="px-3 py-1 bg-zinc-800 rounded-xl text-white disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 📜 Transactions (user only) */}
      {!user?.is_admin && (
        <div className="mt-4">
          <h2 className="font-bold text-white mb-2">Transactions</h2>
          <div className="overflow-x-auto border border-zinc-700 rounded-xl">
            <table className="min-w-[700px] border-collapse border border-zinc-700 text-white">
              <thead>
                <tr className="bg-zinc-800">
                  <th className="px-2 py-1 sticky left-0 bg-zinc-800 z-30 text-left">
                    Type
                  </th>
                  <th className="px-2 py-1 sticky left-[80px] bg-zinc-800 z-30 text-left">
                    Amount
                  </th>
                  <th className="px-2 py-1 sticky top-0 bg-zinc-800 z-20 text-left">
                    Reason
                  </th>
                  <th className="px-2 py-1 sticky top-0 bg-zinc-800 z-20 text-left">
                    Date
                  </th>
                </tr>
              </thead>
              <tbody>
                {transactions
                  .slice(page * pageSize, (page + 1) * pageSize)
                  .map((t) => (
                    <tr key={t.id} className="border-t border-zinc-700">
                      <td className="px-2 py-1 sticky left-0 bg-zinc-900 z-20">
                        {t.type}
                      </td>
                      <td className="px-2 py-1 sticky left-[80px] bg-zinc-900 z-20">
                        ${t.amount.toFixed(2)}
                      </td>
                      <td className="px-2 py-1">{t.reason}</td>
                      <td className="px-2 py-1">
                        {new Date(t.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          <div className="flex justify-between items-center mt-2 px-2">
            <button
              disabled={page === 0}
              onClick={() => setPage(page - 1)}
              className="px-3 py-1 bg-zinc-800 rounded-xl text-white disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <span className="text-sm text-zinc-400">
              Page {page + 1} of {Math.ceil(transactions.length / pageSize)}
            </span>
            <button
              disabled={(page + 1) * pageSize >= transactions.length}
              onClick={() => setPage(page + 1)}
              className="px-3 py-1 bg-zinc-800 rounded-xl text-white disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Logout */}
      {/* <button
        onClick={handleLogout}
        className="w-full flex items-center justify-center gap-2 rounded-xl border border-red-500/40 text-red-400 py-3 hover:bg-red-500/10 transition"
      >
        <LogOut size={18} />
        Logout
      </button> */}
    </div>
  );
};

export default Me;
