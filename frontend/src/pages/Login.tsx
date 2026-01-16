import { useState } from "react";
import { login } from "../services/api";

type Props = {
  onLogin: () => void;
};

const Login = ({ onLogin }: Props) => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const data = await login(email, password);
      localStorage.setItem("token", data.access_token);
      onLogin();
    } catch (err: any) {
      setError(err.message || "Invalid email or password");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-emerald-900 via-black to-black px-4">
      <div className="w-full max-w-md rounded-2xl bg-zinc-900/90 backdrop-blur border border-zinc-800 shadow-2xl p-8">
        <h1 className="text-center text-3xl font-bold text-emerald-400 mb-2">
          BetSmart
        </h1>
        <p className="text-center text-zinc-400 mb-6">Sign in to continue</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="email"
            placeholder="Email address"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-xl bg-zinc-800 px-4 py-3 text-white placeholder-zinc-500 border border-zinc-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
          />

          <input
            type="password"
            placeholder="Password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-xl bg-zinc-800 px-4 py-3 text-white placeholder-zinc-500 border border-zinc-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
          />

          {error && <p className="text-center text-sm text-red-400">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-emerald-600 hover:bg-emerald-700 py-3 font-semibold text-white transition active:scale-[0.98] disabled:opacity-50"
          >
            {loading ? "Signing in..." : "Login"}
          </button>
        </form>

        <div className="mt-6 text-center text-xs text-zinc-500">
          Secure • Fast • Trusted
        </div>
      </div>
    </div>
  );
};

export default Login;
