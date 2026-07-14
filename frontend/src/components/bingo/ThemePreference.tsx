import { Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { useTheme } from "next-themes";

const OPTIONS = [
  { id: "system", label: "System", icon: Monitor },
  { id: "light", label: "Light", icon: Sun },
  { id: "dark", label: "Dark", icon: Moon },
] as const;

/** Compact theme control for the Profile tab — system is default via ThemeProvider. */
export function ThemePreference() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const active = mounted ? (theme ?? "system") : "system";

  return (
    <div className="w-full max-w-sm">
      <p className="mb-2 text-left text-xs font-semibold uppercase tracking-wide text-purple-500 dark:text-purple-300">
        Appearance
      </p>
      <div className="grid grid-cols-3 gap-2 rounded-2xl bg-white/80 p-1.5 ring-1 ring-purple-100 dark:bg-white/5 dark:ring-white/10">
        {OPTIONS.map(({ id, label, icon: Icon }) => {
          const selected = active === id;

          return (
            <button
              key={id}
              type="button"
              onClick={() => setTheme(id)}
              className={`flex flex-col items-center gap-1 rounded-xl px-2 py-2.5 text-xs font-bold transition-all duration-200 ${
                selected
                  ? "bg-[#4C1D95] text-white shadow dark:bg-violet-600"
                  : "text-purple-700 hover:bg-purple-50 dark:text-purple-200 dark:hover:bg-white/10"
              }`}
            >
              <Icon size={18} />
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
