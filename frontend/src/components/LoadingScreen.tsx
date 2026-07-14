import { Gamepad2 } from "lucide-react";

export default function LoadingScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-black via-slate-900 to-purple-950">
      <div className="flex flex-col items-center">
        {/* Fixed square so the spinner is a true concentric ring (no wobble). */}
        <div className="relative h-28 w-28">
          <div className="absolute inset-0 animate-pulse rounded-full bg-purple-500 opacity-40 blur-xl" />

          <div className="absolute inset-0 flex items-center justify-center rounded-full border border-white/20 bg-white/10 backdrop-blur-xl">
            <Gamepad2 size={48} className="text-purple-400" aria-hidden />
          </div>

          {/* Perfect circle border spinner — Gamepad stays still in the center. */}
          <div
            className="absolute inset-0 animate-spin rounded-full border-[3px] border-pink-400/25 border-t-pink-400"
            role="status"
            aria-label="Loading"
          />
        </div>

        <h2 className="mt-8 text-2xl font-black text-white">Telegram Games</h2>
        <p className="mt-2 animate-pulse text-gray-400">Loading your games...</p>
      </div>
    </div>
  );
}
