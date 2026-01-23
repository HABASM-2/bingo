import { useEffect, useState } from "react";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import { API_URL } from "./config/api";

function App() {
  const [loggedIn, setLoggedIn] = useState(!!localStorage.getItem("token"));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const tg = (window as any).Telegram?.WebApp;

    async function telegramLogin() {
      // 1️⃣ Try reading token from URL query params
      const params = new URLSearchParams(window.location.search);
      const tokenFromUrl = params.get("token");
      if (tokenFromUrl) {
        localStorage.setItem("token", tokenFromUrl);
        setLoggedIn(true);
        setLoading(false);
        window.history.replaceState({}, "", "/web"); // clean URL
        return;
      }

      // 2️⃣ If no token, try Telegram WebApp initData
      if (tg && tg.initData) {
        try {
          const res = await fetch(`${API_URL}/auth/telegram-login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ init_data: tg.initData }),
          });

          if (!res.ok) {
            console.log("Telegram login failed", res.status);
            setLoading(false);
            return;
          }

          const data = await res.json();
          if (data.access_token) {
            localStorage.setItem("token", data.access_token);
            setLoggedIn(true);
          } else {
            console.log("No access_token returned from Telegram login");
          }
        } catch (err) {
          console.log("Telegram login error", err);
        } finally {
          setLoading(false);
        }
      } else {
        // 3️⃣ Normal web, not Telegram
        setLoading(false);
      }
    }

    telegramLogin();
  }, []);

  if (loading)
    return <div className="text-white text-center mt-10">Loading...</div>;

  return loggedIn ? <Dashboard /> : <Login onLogin={() => setLoggedIn(true)} />;
}

export default App;
