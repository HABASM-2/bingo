// src/pages/AdminPanel.tsx
import { useState } from "react";

type UpdateBalanceResponse = {
  email: string;
  new_balance: number;
  message: string;
};

const AdminPanel = () => {
  const [email, setEmail] = useState("");
  const [amount, setAmount] = useState<number>(0);
  const [reason, setReason] = useState("");
  const [response, setResponse] = useState<UpdateBalanceResponse | null>(null);
  const [error, setError] = useState("");

  const token = localStorage.getItem("token"); // admin token

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setResponse(null);

    try {
      const res = await fetch("http://127.0.0.1:8000/admin/update-balance", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ user_email: email, amount, reason }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Error updating balance");
      }

      const data = await res.json();
      setResponse(data);
      setEmail("");
      setAmount(0);
      setReason("");
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <div className="max-w-md mx-auto p-4 bg-zinc-900 text-white rounded-xl shadow-lg mt-8">
      <h2 className="text-xl font-bold text-emerald-400 mb-4">
        Admin: Deposit / Withdraw
      </h2>

      <form className="space-y-3" onSubmit={handleSubmit}>
        <input
          type="email"
          placeholder="User Email"
          value={email}
          required
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-xl bg-zinc-800 px-3 py-2 border border-zinc-700"
        />

        <input
          type="number"
          placeholder="Amount (+ deposit, - withdraw)"
          value={amount}
          required
          onChange={(e) => setAmount(parseFloat(e.target.value))}
          className="w-full rounded-xl bg-zinc-800 px-3 py-2 border border-zinc-700"
        />

        <input
          type="text"
          placeholder="Reason / Note"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="w-full rounded-xl bg-zinc-800 px-3 py-2 border border-zinc-700"
        />

        <button
          type="submit"
          className="w-full bg-emerald-600 hover:bg-emerald-700 py-2 rounded-xl font-semibold"
        >
          Update Balance
        </button>
      </form>

      {response && (
        <div className="mt-4 p-3 bg-green-800 rounded-xl">
          <p>{response.message}</p>
          <p>
            <strong>User:</strong> {response.email} <br />
            <strong>New Balance:</strong> {response.new_balance}
          </p>
        </div>
      )}

      {error && (
        <div className="mt-4 p-3 bg-red-800 rounded-xl">
          <p>{error}</p>
        </div>
      )}
    </div>
  );
};

export default AdminPanel;
