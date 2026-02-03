export const t = (lang: "am" | "en") => ({
  // Header & Stats
  called: lang === "am" ? "የተጠሩ" : "Called",
  selectStake: lang === "am" ? "የጨዋታ መጠን ይምረጡ" : "Select Stake",
  stake: lang === "am" ? "ጨዋታ መጠን" : "Stake",
  action: lang === "am" ? "እርምጃ" : "Action",
  join: lang === "am" ? "ግባ" : "Join",
  waiting: lang === "am" ? "ይጠብቁ" : "waiting",
  loading: lang === "am" ? "ይጠብቁ" : "loading",
  status: lang === "am" ? "ሁኔታ" : "Status",
  countdown: lang === "am" ? "መቁጠሪያ" : "Countdown",
  playing: lang === "am" ? "ጨዋታ በመካሄድ ላይ" : "Playing",
  players: lang === "am" ? "ተጫዋቾች" : "Players",
  derash: lang === "am" ? "ድራሽ" : "Derash",
  gameNo: lang === "am" ? "የጨዋታ ቁጥር" : "Game No",
  calledNumbers: lang === "am" ? "የተጠሩ ቁጥሮች" : "Called Numbers",

  // Connecting / Game status
  connecting: lang === "am" ? "ከሰርቨር ጋር በመገናኘት..." : "Connecting to game server...",
  selectNumber: lang === "am" ? "ቁጥር ይምረጡ" : "Select Your Number",
  gameStarted: lang === "am" ? "ጨዋታው ተጀምሯል" : "Game is already started",
  bingoDraw: lang === "am" ? "ቁጥር በመጠራት ላይ" : "BINGO DRAW",
  autoClick: lang === "am" ? "በራስ-ሰር ምልክት አድርግ" : "Auto-Click Numbers",
  bingoBtn: lang === "am" ? "🎉 ቢንጎ!" : "🎉 Bingo!",
  winner: lang === "am" ? "አሸናፊ" : "Bingo Winner",
  you: lang === "am" ? "እርስዎ" : "YOU",

  // Dynamic messages
  selectYourNumber: (s: number) =>
    lang === "am" ? `ቁጥር ይምረጡ (${s} ሰከንድ ቀርቷል)` : `Select your number (${s}s left)`,
  nextCall: (s: number) =>
    lang === "am" ? `ቀጣይ ቁጥር በ ${s} ሰከንድ` : `Next call in ${s}s`,

  // Announcements / Errors
  newRound: lang === "am" ? "አዲስ ዙር ተጀመረ" : "New round started",
  roundCancelled: lang === "am" ? "ዙር ተሰርዟል — ተጫዋቾች ብዛት አልበቃም" : "Round cancelled — not enough players",
  refund: lang === "am" ? "ጨዋታ ተሰርዟል። የጨዋታ ገንዘብ ተመላሽቷል" : "Game canceled. Stake refunded.",
  playerWon: lang === "am" ? "ተጫዋች ቢንጎ አሸናፊ ሆነ!" : "Player won Bingo!",
  alert: lang === "am" ? "ማስጠንቀቂያ" : "Alert",
});
