import CountdownRing from "./CountdownRing";

type Props = {
  number?: number;
  secondsLeft: number;
  totalSeconds: number;
  gameStarting?: boolean; // add this
};

const NumberCaller = ({
  number,
  secondsLeft,
  totalSeconds,
  gameStarting = false,
}: Props) => {
  return (
    <div className="rounded-2xl bg-zinc-900 border border-zinc-800 p-3 space-y-3">
      <div className="flex justify-center">
        <div className="h-20 w-20 rounded-full bg-yellow-400 text-black flex items-center justify-center text-3xl font-bold shadow-[0_0_15px_#facc15]">
          {number ?? "--"}
        </div>
      </div>

      <CountdownRing
        seconds={secondsLeft}
        total={totalSeconds}
        gameStarting={gameStarting}
      />
    </div>
  );
};

export default NumberCaller;
