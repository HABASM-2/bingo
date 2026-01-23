// src/components/StakeSelector.tsx

type Props = {
  currentStake: number;
  availableStakes: number[];
  onChange: (stake: number) => void;
  gameStarted: boolean;
};

const StakeSelector = ({
  currentStake,
  availableStakes,
  onChange,
  gameStarted,
}: Props) => {
  return (
    <div className="flex items-center gap-2 mb-3 justify-center">
      <span className="text-white font-semibold">Select Stake:</span>
      {availableStakes.map((s) => (
        <button
          key={s}
          onClick={() => onChange(s)}
          disabled={gameStarted} // ❌ disable after game starts
          className={`px-3 py-1 rounded-full font-bold transition 
            ${currentStake === s ? "bg-emerald-400 text-black" : "bg-zinc-800 text-white"}
            ${gameStarted ? "opacity-50 cursor-not-allowed" : "hover:bg-emerald-500"}`}
        >
          {s}
        </button>
      ))}
    </div>
  );
};

export default StakeSelector;
