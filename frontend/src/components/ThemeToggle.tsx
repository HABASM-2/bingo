import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useI18n } from "../i18n";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const { t } = useI18n();

  const itemStyle = (value: string) =>
    `
    flex
    items-center
    gap-2
    w-full
    rounded-xl
    px-3
    py-2
    transition-all
    duration-200
    ${
      theme === value
        ? "bg-violet-600 text-white"
        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10"
    }
  `;

  return (
    <div
      className="
      rounded-2xl
      bg-white
      dark:bg-[#171721]
      border
      border-gray-200
      dark:border-white/10
      p-2
      shadow-xl
      w-48
      "
    >
      <button onClick={() => setTheme("light")} className={itemStyle("light")}>
        <Sun size={18} />
        {t("theme.light")}
      </button>

      <button onClick={() => setTheme("dark")} className={itemStyle("dark")}>
        <Moon size={18} />
        {t("theme.dark")}
      </button>

      <button
        onClick={() => setTheme("system")}
        className={itemStyle("system")}
      >
        <Monitor size={18} />
        {t("theme.system")}
      </button>
    </div>
  );
}
