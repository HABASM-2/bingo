import { Gamepad2, Plane, Target, User } from "lucide-react";

export type NavTab = "bingo" | "keno" | "fly" | "profile";

interface BottomNavProps {
  active: NavTab;
  onChange: (tab: NavTab) => void;
}

const TABS: { id: NavTab; label: string; icon: typeof Gamepad2; disabled?: boolean }[] = [
  { id: "bingo", label: "Bingo", icon: Gamepad2 },
  { id: "keno", label: "Keno", icon: Target, disabled: true },
  { id: "fly", label: "Fly", icon: Plane, disabled: true },
  { id: "profile", label: "Profile", icon: User },
];

export function BottomNav({ active, onChange }: BottomNavProps) {
  return (
    <nav className="border-t border-purple-200/80 bg-[#E7DEF6]/95 px-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur-md dark:border-white/10 dark:bg-[#14121F]/95">
      <div className="flex justify-between gap-1 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {TABS.map(({ id, label, icon: Icon, disabled }) => {
          const isActive = active === id;

          return (
            <button
              key={id}
              type="button"
              disabled={disabled}
              onClick={() => onChange(id)}
              className={`flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-2xl px-2 py-2 text-[11px] font-bold tracking-wide transition-all duration-200 ${
                isActive
                  ? "bg-[#4C1D95] text-white shadow-md shadow-purple-900/25 dark:bg-violet-600"
                  : disabled
                    ? "text-purple-300 dark:text-white/25"
                    : "text-purple-700 hover:bg-white/60 active:scale-95 dark:text-purple-200 dark:hover:bg-white/10"
              }`}
            >
              <Icon size={18} strokeWidth={isActive ? 2.5 : 2} />
              {label}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
