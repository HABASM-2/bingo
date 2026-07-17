interface TelegramWebApp {
  initData: string;
  initDataUnsafe: {
    user?: {
      id: number;
      first_name: string;
      username?: string;
      language_code?: string;
    };
    /** Present when opened via t.me/Bot?startapp=… or startapp deep link. */
    start_param?: string;
  };

  ready(): void;
  expand(): void;
  close?: () => void;
}

interface Window {
  Telegram?: {
    WebApp: TelegramWebApp;
  };
}
