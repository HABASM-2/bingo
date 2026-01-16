import { Home, ListOrdered, User } from "lucide-react";

type Props = {
  active: "dashboard" | "history" | "me";
  onChange: (tab: Props["active"]) => void;
};

const BottomNav = ({ active, onChange }: Props) => {
  const itemClass = (tab: Props["active"]) =>
    `flex flex-col items-center gap-1 text-xs transition
     ${active === tab ? "text-emerald-400" : "text-zinc-400 hover:text-white"}`;

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 bg-zinc-900/95 backdrop-blur border-t border-zinc-800">
      <div className="flex justify-around py-2">
        <button
          onClick={() => onChange("dashboard")}
          className={itemClass("dashboard")}
        >
          <Home size={22} />
          Dashboard
        </button>

        <button
          onClick={() => onChange("history")}
          className={itemClass("history")}
        >
          <ListOrdered size={22} />
          History
        </button>

        <button onClick={() => onChange("me")} className={itemClass("me")}>
          <User size={22} />
          Me
        </button>
      </div>
    </nav>
  );
};

export default BottomNav;
