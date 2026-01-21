import { useEffect, useState } from "react";
import BottomNav from "../components/BottomNav";
import DashboardHome from "./Home";
import History from "./History";
import Me from "./Me";

const STAKE_KEY = "bingo_stake";

const Dashboard = () => {
  const [tab, setTab] = useState<"dashboard" | "history" | "me">("dashboard");

  const [stake, setStake] = useState<number>(() => {
    const saved = localStorage.getItem(STAKE_KEY);
    return saved ? Number(saved) : 10;
  });

  // 🔥 persist whenever stake changes
  useEffect(() => {
    localStorage.setItem(STAKE_KEY, String(stake));
  }, [stake]);

  return (
    <div className="min-h-screen bg-black text-white pb-20">
      {tab === "dashboard" && (
        <DashboardHome stake={stake} setStake={setStake} />
      )}
      {tab === "history" && <History />}
      {tab === "me" && <Me />}

      <BottomNav active={tab} onChange={setTab} />
    </div>
  );
};

export default Dashboard;
