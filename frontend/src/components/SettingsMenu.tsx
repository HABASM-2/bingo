import { useState } from "react";
import { Settings, X } from "lucide-react";
import { ThemeToggle } from "./ThemeToggle";

export function SettingsMenu() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="
        h-12
        w-12
        rounded-2xl
        bg-white/10
        border
        border-white/10
        flex
        items-center
        justify-center
        backdrop-blur-xl
        hover:bg-white/20
        transition
        "
      >
        <Settings size={22} />
      </button>

      {open && (
        <>
          <div
            className="
            fixed
            inset-0
            bg-black/50
            z-40
            "
            onClick={() => setOpen(false)}
          />

          <div
            className="
            fixed
            right-4
            top-4
            z-50
            w-72
            rounded-3xl
            bg-white
            dark:bg-[#171721]
            text-gray-900
            dark:text-white
            border
            border-gray-200
            dark:border-white/10
            shadow-2xl
            overflow-hidden
            "
          >
            <div
              className="
              flex
              items-center
              justify-between
              p-5
              border-b
              border-gray-200
              dark:border-white/10
              "
            >
              <h2 className="text-lg font-bold">Settings</h2>

              <button
                onClick={() => setOpen(false)}
                className="
                rounded-lg
                p-2
                hover:bg-gray-100
                dark:hover:bg-white/10
                "
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-5">
              <p
                className="
              text-sm
              text-gray-500
              dark:text-gray-400
              mb-3
              "
              >
                Appearance
              </p>

              <ThemeToggle />
            </div>
          </div>
        </>
      )}
    </>
  );
}
