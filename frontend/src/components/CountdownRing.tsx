type Props = {
  seconds: number;
  total: number;
  gameStarting?: boolean; // true if countdown is before game starts
};

const CountdownRing = ({ seconds, total, gameStarting = false }: Props) => {
  const percent = (seconds / total) * 100;

  return (
    <div className="w-full">
      <div className="h-2 w-full bg-zinc-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-emerald-500 transition-all duration-1000"
          style={{ width: `${percent}%` }}
        />
      </div>
      <p className="mt-1 text-center text-xs text-zinc-400">
        {gameStarting
          ? `Game starts in ${seconds}s`
          : `Next call in ${seconds}s`}
      </p>
    </div>
  );
};

export default CountdownRing;
