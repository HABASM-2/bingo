import { useState } from "react";
import BottomNav from "../components/BottomNav";
import DashboardHome from "./Home";
import History from "./History";
import Me from "./Me";

const Dashboard = () => {
  const [tab, setTab] = useState<"dashboard" | "history" | "me">("dashboard");

  return (
    <div className="min-h-screen bg-black text-white pb-20">
      {tab === "dashboard" && <DashboardHome />}
      {tab === "history" && <History />}
      {tab === "me" && <Me />}

      <BottomNav active={tab} onChange={setTab} />
    </div>
  );
};

export default Dashboard;
