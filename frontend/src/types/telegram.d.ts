interface TelegramWebApp {
  initData: string;
  initDataUnsafe: {
    user?: {
      id: number;
      first_name: string;
      username?: string;
    };
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