import { Volume2, VolumeX } from "lucide-react";

type Props = {
  gameNo: number;
  derash: number;
  players: number;
  called: number;
  muted: boolean;
  onToggleMute: () => void;
};

const Stat = ({ label, value }: { label: string; value: string | number }) => (
  <div className="flex flex-col items-center flex-1">
    <span className="text-[10px] text-zinc-400 uppercase">{label}</span>
    <span className="text-sm font-bold text-white">{value}</span>
  </div>
);

const DashboardHeader = ({
  gameNo,
  derash,
  players,
  called,
  muted,
  onToggleMute,
}: Props) => {
  return (
    <div className="flex items-center justify-between bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-2">
      <Stat label="Game No" value={gameNo.toString().padStart(6, "0")} />
      <Stat label="Derash" value={derash} />
      <Stat label="Player" value={players} />
      <Stat label="Called" value={called} />

      <button
        onClick={onToggleMute}
        className="flex items-center justify-center h-9 w-9 rounded-full bg-zinc-800 hover:bg-zinc-700 transition"
      >
        {muted ? (
          <VolumeX size={18} className="text-red-400" />
        ) : (
          <Volume2 size={18} className="text-emerald-400" />
        )}
      </button>
    </div>
  );
};

export default DashboardHeader;
