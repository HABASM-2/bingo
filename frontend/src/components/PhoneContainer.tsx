type Props = {
  children: React.ReactNode;
};

const PhoneContainer = ({ children }: Props) => {
  return (
    <div className="min-h-screen flex items-center justify-center bg-black">
      <div className="w-full max-w-[480px] h-[100svh] bg-zinc-950 border border-zinc-800 rounded-none sm:rounded-3xl overflow-hidden shadow-xl">
        {children}
      </div>
    </div>
  );
};

export default PhoneContainer;
