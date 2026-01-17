type Props = {
  children: React.ReactNode;
};

const PhoneContainer = ({ children }: Props) => {
  return (
    <div className="min-h-screen flex flex-col items-center justify-start bg-black">
      <div className="w-full max-w-[480px] flex-1 bg-zinc-950 border border-zinc-800 rounded-none sm:rounded-3xl overflow-hidden flex flex-col">
        {children}
      </div>
    </div>
  );
};

export default PhoneContainer;
