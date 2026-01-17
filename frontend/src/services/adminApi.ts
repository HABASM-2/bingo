// const API_URL = "http://10.55.29.239:8000";
import { API_URL } from "../config/api";

export async function getUsers() {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API_URL}/auth/users`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to fetch users");
  return res.json();
}

export async function manualDeposit(payload: { user_id: string; amount: number }) {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API_URL}/auth/deposit`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Deposit failed");
  return res.json();
}

export async function manualWithdraw(payload: { user_id: string; amount: number }) {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API_URL}/auth/withdraw`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Withdraw failed");
  return res.json();
}

export async function getUserTransactions(userId: string) {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API_URL}/auth/user/${userId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to fetch transactions");
  return res.json();
}
