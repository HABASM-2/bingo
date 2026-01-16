const API_URL = "http://127.0.0.1:8000";

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
  data: { user_email: string; amount: number; reason: string }
) {
  const res = await fetch(`${API_URL}/admin/update-balance`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
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