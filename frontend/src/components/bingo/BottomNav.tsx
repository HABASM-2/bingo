import { useEffect, useRef } from "react";
import { Crown, Gamepad2, Home, Plane, User } from "lucide-react";

export type NavTab = "home" | "bingo" | "dama" | "aviator" | "profile";

interface BottomNavProps {
  active: NavTab;
  onChange: (tab: NavTab) => void;
  /** Pulse the Bingo chip while a round is live. */
  bingoLive?: boolean;
}

const SCROLL_TABS: {
  id: Exclude<NavTab, "profile">;
  label: string;
  icon: typeof Gamepad2;
}[] = [
  { id: "home", label: "Home", icon: Home },
  { id: "bingo", label: "Bingo", icon: Gamepad2 },
  { id: "dama", label: "Dama", icon: Crown },
  { id: "aviator", label: "Aviator", icon: Plane },
];

export function BottomNav({ active, onChange, bingoLive = false }: BottomNavProps) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<Partial<Record<NavTab, HTMLButtonElement | null>>>({});

  useEffect(() => {
    if (active === "profile") return;
    const el = itemRefs.current[active];
    el?.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
  }, [active]);

  return (
    <nav className="relative z-30 border-t border-purple-200/80 bg-[#E7DEF6]/95 pb-[max(0.45rem,env(safe-area-inset-bottom))] pt-1.5 backdrop-blur-md dark:border-white/10 dark:bg-[#14121F]/95">
      <div className="relative flex items-stretch gap-0 px-1.5">
        <div className="relative min-w-0 flex-1">
          <div
            ref={scrollerRef}
            className="flex gap-1 overflow-x-auto px-1 pb-0.5 pt-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          >
            {SCROLL_TABS.map(({ id, label, icon: Icon }) => {
              const isActive = active === id;

              return (
                <button
                  key={id}
                  ref={(node) => {
                    itemRefs.current[id] = node;
                  }}
                  type="button"
                  onClick={() => onChange(id)}
                  className={`relative flex w-[4.35rem] shrink-0 flex-col items-center gap-0.5 rounded-2xl px-1.5 py-1.5 text-[10px] font-bold tracking-wide transition-all duration-200 ${
                    isActive
                      ? "bg-[#4C1D95] text-white shadow-md shadow-purple-900/25 dark:bg-violet-600"
                      : "text-purple-700 hover:bg-white/55 active:scale-95 dark:text-purple-200 dark:hover:bg-white/10"
                  }`}
                >
                  <Icon size={17} strokeWidth={isActive ? 2.5 : 2} />
                  <span className="leading-none">{label}</span>
                  {id === "bingo" && bingoLive && (
                    <span
                      className={`absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full ${
                        isActive ? "bg-emerald-300" : "bg-emerald-500"
                      } animate-pulse`}
                      aria-hidden
                    />
                  )}
                </button>
              );
            })}
          </div>

          <div
            className="pointer-events-none absolute inset-y-0 right-0 w-8 bg-gradient-to-l from-[#E7DEF6] via-[#E7DEF6]/70 to-transparent dark:from-[#14121F] dark:via-[#14121F]/70"
            aria-hidden
          />
        </div>

        <div
          className="pointer-events-none absolute bottom-0 top-0 right-[4.55rem] z-[5] w-6 bg-gradient-to-r from-transparent to-purple-950/20 dark:to-black/50"
          aria-hidden
        />

        <button
          type="button"
          onClick={() => onChange("profile")}
          className={`relative z-10 ml-0.5 flex w-[4.4rem] shrink-0 flex-col items-center gap-0.5 rounded-2xl px-1.5 py-1.5 text-[10px] font-bold tracking-wide transition-all duration-200 ${
            active === "profile"
              ? "bg-[#4C1D95] text-white shadow-md shadow-purple-900/25 dark:bg-violet-600"
              : "bg-white/75 text-purple-700 ring-1 ring-purple-200/80 hover:bg-white active:scale-95 dark:bg-white/10 dark:text-purple-200 dark:ring-white/10"
          }`}
        >
          <User size={17} strokeWidth={active === "profile" ? 2.5 : 2} />
          <span className="leading-none">Profile</span>
        </button>
      </div>

      <p className="px-3 pb-0.5 pt-0.5 text-center text-[9px] font-medium text-purple-400/90 dark:text-purple-300/50">
        Swipe for more games
      </p>
    </nav>
  );
}
