import type { LucideIcon } from "lucide-react";
import { Users, Play, Lock } from "lucide-react";
import { useI18n } from "../i18n";

type Game = {
  name: string;
  description: string;
  players: string;
  status: string;
  icon: LucideIcon;
};

interface GameCardProps {
  game: Game;
  onPlay: () => void;
}

export function GameCard({ game, onPlay }: GameCardProps) {
  const { t } = useI18n();
  const Icon = game.icon;

  const live = game.status === "LIVE";

  return (
    <div
      className="
      group
      relative
      overflow-hidden
      rounded-3xl
      bg-white
      dark:bg-white/5
      border
      border-gray-200
      dark:border-white/10
      transition-all
      duration-300
      hover:-translate-y-1
      hover:border-violet-500/50
      hover:shadow-[0_0_30px_rgba(139,92,246,0.35)]
      "
    >
      {/* Glow */}
      <div
        className="
        absolute
        -top-12
        -right-12
        h-36
        w-36
        rounded-full
        bg-violet-500/20
        blur-3xl
        group-hover:bg-pink-500/30
        transition-all
        duration-500
        "
      />

      {/* Cover */}
      <div
        className="
        relative
        h-36
        bg-gradient-to-br
        from-violet-600
        via-purple-600
        to-pink-600
        flex
        items-center
        justify-center
        overflow-hidden
        "
      >
        <Icon
          size={70}
          className="
          text-white
          transition-transform
          duration-300
          group-hover:scale-110
          group-hover:rotate-6
          "
        />

        {live ? (
          <div
            className="
            absolute
            top-3
            right-3
            rounded-full
            bg-green-400
            px-3
            py-1
            text-[11px]
            font-bold
            text-black
            animate-pulse
            "
          >
            {t("gameCard.live")}
          </div>
        ) : (
          <div
            className="
            absolute
            top-3
            right-3
            rounded-full
            bg-black/40
            px-3
            py-1
            text-[11px]
            font-semibold
            text-white
            "
          >
            {t("gameCard.soon")}
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4">
        <h2
          className="
          text-lg
          font-bold
          text-gray-900
          dark:text-white
          "
        >
          {game.name}
        </h2>

        <p
          className="
          mt-1
          text-sm
          text-gray-500
          dark:text-gray-400
          "
        >
          {game.description}
        </p>

        <div
          className="
          mt-4
          flex
          items-center
          justify-between
          text-sm
          text-gray-600
          dark:text-gray-300
          "
        >
          <div className="flex items-center gap-1">
            <Users size={15} />

            {game.players}
          </div>

          {live && (
            <span
              className="
              text-green-500
              font-semibold
              "
            >
              {t("gameCard.online")}
            </span>
          )}
        </div>

        <button
          type="button"
          disabled={!live}
          onClick={() => {
            if (live) {
              onPlay();
            }
          }}
          className={`
            mt-5
            flex
            w-full
            items-center
            justify-center
            gap-2
            rounded-2xl
            py-3
            font-bold
            transition-all
            duration-300

            ${
              live
                ? `
                bg-gradient-to-r
                from-violet-500
                to-fuchsia-500
                hover:scale-[1.03]
                active:scale-95
                shadow-lg
                shadow-violet-500/30
                text-white
                `
                : `
                bg-gray-200
                dark:bg-gray-700
                text-gray-400
                dark:text-gray-400
                cursor-not-allowed
                `
            }
          `}
        >
          {live ? (
            <>
              <Play size={18} />
              {t("gameCard.playNow")}
            </>
          ) : (
            <>
              <Lock size={18} />
              {t("gameCard.comingSoon")}
            </>
          )}
        </button>
      </div>
    </div>
  );
}
