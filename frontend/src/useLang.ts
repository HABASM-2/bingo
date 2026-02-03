import { useEffect, useState } from "react";

export type Lang = "am" | "en";

export const useLang = () => {
  const [lang, setLang] = useState<Lang>(() => {
    return (localStorage.getItem("lang") as Lang) || "am"; // ✅ Default Amharic
  });

  useEffect(() => {
    localStorage.setItem("lang", lang);
  }, [lang]);

  return { lang, setLang };
};
