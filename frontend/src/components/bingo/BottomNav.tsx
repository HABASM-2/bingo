import { useEffect, useRef } from "react";
import { CircleDot, Crown, Gamepad2, Home, Plane, RotateCw, ShieldCheck, User } from "lucide-react";
import { useI18n, type TranslationKey } from "../../i18n";

export type NavTab = "home" | "bingo" | "dama" | "aviator" | "plinko" | "lotto" | "profile" | "admin";

interface BottomNavProps {
  active: NavTab;
  onChange: (tab: NavTab) => void;
  /** Pulse the Bingo chip while a round is live. */
  bingoLive?: boolean;
  isAdmin?: boolean;
}

const NAV_TABS: {
  id: NavTab;
  labelKey: TranslationKey;
  icon: typeof Gamepad2;
}[] = [
  { id: "home", labelKey: "nav.home", icon: Home },
  { id: "bingo", labelKey: "nav.bingo", icon: Gamepad2 },
  { id: "dama", labelKey: "nav.dama", icon: Crown },
  { id: "aviator", labelKey: "nav.aviator", icon: Plane },
  { id: "plinko", labelKey: "nav.plinko", icon: CircleDot },
  { id: "lotto", labelKey: "nav.lotto", icon: RotateCw },
  { id: "profile", labelKey: "nav.profile", icon: User },
  { id: "admin", labelKey: "nav.admin", icon: ShieldCheck },
];

export function BottomNav({ active, onChange, bingoLive = false, isAdmin = false }: BottomNavProps) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<Partial<Record<NavTab, HTMLButtonElement | null>>>({});
  const { t } = useI18n();

  useEffect(() => {
    const scroller = scrollerRef.current;
    const el = itemRefs.current[active];
    if (!scroller || !el) return;

    const centeredLeft =
      el.offsetLeft - (scroller.clientWidth - el.offsetWidth) / 2;
    const reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    scroller.scrollTo({
      left: Math.max(0, centeredLeft),
      behavior: reducedMotion ? "auto" : "smooth",
    });
  }, [active]);

  return (
    <nav className="relative z-30 border-t border-purple-200/70 bg-[#E7DEF6]/90 pb-[max(0.4rem,env(safe-area-inset-bottom))] pt-1.5 shadow-[0_-8px_24px_rgba(76,29,149,0.08)] backdrop-blur-xl dark:border-white/10 dark:bg-[#14121F]/90 dark:shadow-[0_-8px_24px_rgba(0,0,0,0.28)]">
      <div
        ref={scrollerRef}
        className="flex touch-pan-x snap-x snap-proximity gap-1.5 overflow-x-auto overscroll-x-contain px-3 py-0.5 [-ms-overflow-style:none] [-webkit-overflow-scrolling:touch] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {NAV_TABS.filter(({ id }) => id !== "admin" || isAdmin).map(({ id, labelKey, icon: Icon }) => {
          const isActive = active === id;
          const label = t(labelKey);

          return (
            <button
              key={id}
              ref={(node) => {
                itemRefs.current[id] = node;
              }}
              type="button"
              onClick={() => onChange(id)}
              aria-current={isActive ? "page" : undefined}
              aria-label={label}
              title={label}
              className={`relative flex min-h-11 w-[4.5rem] shrink-0 snap-center flex-col items-center justify-center gap-1 rounded-xl px-1.5 py-1 text-[10px] font-semibold tracking-wide outline-none transition-[background-color,color,box-shadow,transform] duration-200 focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:ring-offset-1 focus-visible:ring-offset-[#E7DEF6] active:scale-[0.97] motion-reduce:transition-none dark:focus-visible:ring-violet-400 dark:focus-visible:ring-offset-[#14121F] ${
                isActive
                  ? "bg-white/85 text-violet-800 shadow-sm ring-1 ring-purple-200/80 dark:bg-violet-500/20 dark:text-violet-200 dark:ring-violet-400/25"
                  : "text-purple-700/75 hover:bg-white/50 hover:text-purple-900 dark:text-purple-200/65 dark:hover:bg-white/[0.07] dark:hover:text-purple-100"
              }`}
            >
              <Icon
                size={18}
                strokeWidth={isActive ? 2.5 : 2}
                className={isActive ? "text-violet-600 dark:text-violet-300" : ""}
                aria-hidden
              />
              <span className="w-full truncate leading-none">{label}</span>
              <span
                className={`absolute bottom-0.5 h-0.5 w-4 rounded-full bg-violet-600 transition-opacity dark:bg-violet-300 ${
                  isActive ? "opacity-100" : "opacity-0"
                }`}
                aria-hidden
              />
              {id === "bingo" && bingoLive && (
                <span
                  className={`absolute right-2 top-1.5 h-1.5 w-1.5 rounded-full ${
                    isActive ? "bg-emerald-400" : "bg-emerald-500"
                  } animate-pulse`}
                  aria-hidden
                />
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
