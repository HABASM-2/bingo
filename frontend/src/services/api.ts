import { API_URL } from "../config/api";

export async function login(email: string, password: string) {
  const res = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error("Invalid email or password");
  return res.json();
}

export async function getMe(token: string) {
  const res = await fetch(`${API_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Unauthorized");
  return res.json();
}

// Admin: update balance (deposit/withdraw)
export async function updateBalance(
  token: string,
  data: { user_id: string; amount: number; note?: string } // match WalletAction
) {
  const res = await fetch(`${API_URL}/auth/deposit`, {
    method: "POST",
    headers: { 
      "Content-Type": "application/json", 
      Authorization: `Bearer ${token}` 
    },
    body: JSON.stringify(data),
  });

  if (!res.ok) {
    const errorData = await res.json();
    throw new Error(errorData.detail || "Failed to update balance");
  }
  return res.json();
}

// Normal users: get own transactions
export async function getMyTransactions() {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API_URL}/auth/transactions`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to fetch transactions");
  return res.json();
}

export async function requestWithdraw(token: string, amount: number, note?: string) {
  return fetch("/auth/withdraw/request", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ amount, note }), // ✅ match UserWithdrawRequest schema
  });
}

export async function cancelWithdraw(token: string, txId: string) {
  const res = await fetch(`/auth/withdraw/cancel/${txId}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) throw new Error("Cancel failed");
  return res.json();
}

export async function getAllWithdraws(token: string, skip = 0, limit = 10) {
  const res = await fetch(`${API_URL}/auth/admin/withdraws?skip=${skip}&limit=${limit}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to fetch withdraws");
  return res.json(); // returns { total, skip, limit, withdraws }
}

export async function updateWithdrawStatus(
  token: string,
  txId: string,
  status: string
) {
  const res = await fetch(
    `/auth/admin/withdraw/update/${txId}?status=${status}`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }
  );

  if (!res.ok) throw new Error("Failed to update status");
  return res.json();
}