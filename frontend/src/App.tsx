import { useAuth } from "./hooks/useAuth";
import LoadingScreen from "./components/LoadingScreen";
import { Send } from "lucide-react";
import { SettingsMenu } from "./components/SettingsMenu";
import BingoGame from "./components/bingo/BingoGame";
import { useI18n } from "./i18n";

export default function App() {
  const { user, token, loading } = useAuth();
  const { t } = useI18n();

  if (loading) {
    return <LoadingScreen />;
  }

  if (!user || !token) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#E7DEF6] px-6">
        <div className="w-full max-w-md rounded-3xl bg-white p-8 text-center shadow-xl">
          <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-violet-500/20">
            <Send className="text-violet-500" size={42} />
          </div>

          <h1 className="mt-6 text-3xl font-bold text-gray-900">{t("app.title")}</h1>

          <p className="mt-4 text-gray-500">{t("app.openFromTelegram")}</p>

          <div className="mt-6">
            <SettingsMenu />
          </div>
        </div>
      </div>
    );
  }

  return (
    <BingoGame
      key={user.id}
      userId={String(user.id)}
      firstName={user.first_name ?? t("app.defaultPlayer")}
      authBalance={user.balance}
      accessToken={token}
    />
  );
}
