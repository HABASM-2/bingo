"""Bot message dictionaries — locales match the Mini App (en | am)."""

from __future__ import annotations

from typing import Any

from app.bot.locale import DEFAULT_LOCALE, normalize_locale

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        # Commands (BotFather / set_my_commands)
        "cmd.start": "Welcome & main menu",
        "cmd.play": "Open games menu",
        "cmd.games": "Browse all games",
        "cmd.bingo": "Play Bingo",
        "cmd.dama": "Play Dama",
        "cmd.aviator": "Play Aviator",
        "cmd.plinko": "Play Plinko",
        "cmd.lotto": "Play Lotto Spin",
        "cmd.balance": "Check wallet balance",
        "cmd.language": "Switch English / Amharic",
        "cmd.help": "How to use the bot",
        "cmd.deposit": "Deposit funds",
        "cmd.withdraw": "Withdraw funds",
        "cmd.invite": "Invite friends",
        # Buttons
        "btn.play_games": "Play Games",
        "btn.play": "Open App",
        "btn.play_bingo": "Play Bingo",
        "btn.play_dama": "Play Dama",
        "btn.play_aviator": "Play Aviator",
        "btn.play_plinko": "Play Plinko",
        "btn.play_lotto": "Play Lotto",
        "btn.balance": "Balance",
        "btn.deposit": "Deposit",
        "btn.withdraw": "Withdraw",
        "btn.transfer": "Transfer",
        "btn.register": "Register",
        "btn.invite": "Invite",
        "btn.help": "Help",
        "btn.language": "Language",
        "btn.support": "Support",
        "btn.home": "Home",
        "btn.back": "Back",
        "btn.paid": "I've Paid",
        "btn.confirm": "Confirm",
        "btn.cancel": "Cancel",
        "btn.lang_en": "English",
        "btn.lang_am": "አማርኛ",
        "btn.contact_support": "Contact Support",
        "btn.cancel_pending_withdraw": "Cancel Pending Withdrawal",
        # Menus
        "welcome": (
            "<b>Welcome, {name}!</b>\n\n"
            "<b>BRIGHT GAMES</b>\n"
            "Bingo · Dama · Aviator · Plinko · Lotto\n\n"
            "{referral}"
            "Choose an option below to get started."
        ),
        "welcome.referral": (
            "<b>You joined with an invite link!</b>\n"
            "Register to claim your welcome bonus.\n\n"
        ),
        "menu.home": "<b>Main Menu</b>\n\nBRIGHT GAMES — pick an option:",
        "menu.games": (
            "<b>Games</b>\n\n"
            "Open a game directly in the Mini App:"
        ),
        "game.bingo.blurb": "Classic Ethiopian bingo boards",
        "game.dama.blurb": "Ethiopian checkers — play online",
        "game.aviator.blurb": "Cash out before the crash",
        "game.plinko.blurb": "Drop the ball, hit multipliers",
        "game.lotto.blurb": "Spin for shared pot prizes",
        "open.game": (
            "<b>{title}</b>\n\n"
            "{blurb}\n\n"
            "Tap below to open the Mini App."
        ),
        "language.prompt": (
            "<b>Language</b>\n\n"
            "Current: <b>{current}</b>\n\n"
            "Choose English or አማርኛ."
        ),
        "language.changed": "Language set to <b>{label}</b>.",
        "language.label.en": "English",
        "language.label.am": "አማርኛ",
        "help": (
            "<b>Help — BRIGHT GAMES</b>\n\n"
            "<b>Commands</b>\n"
            "/start — main menu\n"
            "/play or /games — game list\n"
            "/bingo /dama /aviator /plinko /lotto — open a game\n"
            "/balance — wallet\n"
            "/language — English or አማርኛ\n"
            "/help — this message\n\n"
            "<b>Getting started</b>\n"
            "1. Register your account\n"
            "2. Deposit to your wallet\n"
            "3. Open a game from the menu\n\n"
            "Minimum deposit: <b>10 ETB</b>\n"
            "Minimum withdrawal: <b>100 ETB</b>"
        ),
        "balance": (
            "<b>Your Balance</b>\n\n"
            "<b>{balance} ETB</b>"
            "{pending}"
            "\n\nReady to play?"
        ),
        "balance.pending": (
            "\n\n──────────────\n\n"
            "<b>Pending Withdrawal</b>\n"
            "Amount: <b>{amount} ETB</b>\n"
            "Method: <b>{method}</b>\n"
            "Status: <b>{status}</b>"
        ),
        "err.not_registered": "Please register first.",
        "err.user_not_found": "Account not found. Tap Register to create one.",
        "err.generic": "Something went wrong. Try again.",
        "register.already": "You are already registered. Your profile is up to date.",
        "register.updated": (
            "<b>Profile updated</b>\n\n"
            "Synced from Telegram:\n\n{fields}"
        ),
        "register.success": (
            "<b>Registration successful!</b>\n\n"
            "Name: <b>{name}</b>\n"
            "Username: <b>{username}</b>\n"
            "Referral code: <code>{code}</code>\n\n"
            "Welcome bonus: <b>10 ETB</b>"
        ),
        "register.referral_notify": (
            "<b>Referral bonus!</b>\n\n"
            "Your friend <b>{name}</b> registered with your link.\n"
            "You received: <b>10 ETB</b>"
        ),
        "invite": (
            "<b>Invite friends</b>\n\n"
            "Share your link:\n"
            "<code>{link}</code>\n\n"
            "Friend gets <b>10 ETB</b> welcome bonus.\n"
            "You get <b>10 ETB</b> per signup."
        ),
        "support": (
            "<b>Support</b>\n\n"
            "We can help with deposits, withdrawals, games, and account issues.\n"
            "Tap below to message support."
        ),
        "deposit.menu": "<b>Deposit</b>\n\nChoose a payment method:",
        "deposit.method": (
            "{title}\n\n"
            "<b>Account name</b>\n{account_name}\n\n"
            "<b>Account / phone</b>\n<code>{account_number}</code>\n\n"
            "<b>Minimum</b>\n10 ETB\n\n"
            "<b>Steps</b>\n"
            "1. Send money to the account above.\n"
            "2. Save the confirmation SMS.\n"
            "3. Press <b>I've Paid</b>.\n"
            "4. Forward the SMS to this bot."
        ),
        "deposit.forward_sms": "Forward your Telebirr confirmation SMS now.",
        "deposit.success": (
            "<b>Deposit successful</b>\n\n"
            "Amount: <b>{amount} ETB</b>\n"
            "Transaction: <code>{tx}</code>\n\n"
            "Your balance has been updated."
        ),
        "deposit.invalid_sms": "Invalid SMS. Please forward the correct confirmation.",
        "deposit.tx_not_found": "Transaction not found. Wait a moment and try again.",
        "deposit.tx_used": "This transaction was already used.",
        "transfer.ask_user": "Enter the receiver’s Telegram username.\n\nExample:\n@username",
        "transfer.ask_amount": "Receiver found: @{username}\n\nEnter amount:",
        "transfer.confirm": (
            "<b>Confirm transfer</b>\n\n"
            "To: @{username}\n"
            "Amount: <b>{amount} ETB</b>"
        ),
        "transfer.done": (
            "<b>Transfer completed</b>\n\n"
            "Sent: <b>{amount} ETB</b>\n"
            "To: @{username}\n"
            "Remaining: <b>{balance} ETB</b>"
        ),
        "transfer.received": (
            "<b>You received a transfer</b>\n\n"
            "Amount: <b>{amount} ETB</b>\n"
            "From: @{username}\n"
            "New balance: <b>{balance} ETB</b>"
        ),
        "transfer.cancelled": "Transfer cancelled.",
        "transfer.expired": "This transfer has expired.",
        "transfer.missing": "Transfer data missing. Start again.",
        "transfer.self": "You cannot transfer to yourself.",
        "transfer.not_found": "User not found.",
        "transfer.invalid_amount": "Invalid amount.",
        "transfer.amount_positive": "Amount must be greater than zero.",
        "transfer.failed": "Transfer failed. Try again.",
        "transfer.insufficient": "Not enough balance.",
        "withdraw.select": "<b>Select withdrawal method</b>",
        "withdraw.pending": (
            "<b>Withdraw</b>\n\n"
            "You already have a pending withdrawal.\n\n"
            "Amount: <b>{amount} ETB</b>\n"
            "Method: <b>{method}</b>\n\n"
            "Cancel it before submitting another request."
        ),
        "withdraw.ask_name": "Enter the account holder’s full name.",
        "withdraw.ask_number": "Enter your account / phone number.",
        "withdraw.ask_amount": "Enter withdrawal amount.\n\nMinimum: <b>100 ETB</b>",
        "withdraw.confirm": (
            "<b>Confirm withdrawal</b>\n\n"
            "Method: {method}\n"
            "Account name: {name}\n"
            "Account number: {number}\n"
            "Amount: <b>{amount} ETB</b>"
        ),
        "withdraw.submitted": (
            "<b>Withdrawal request submitted</b>\n\n"
            "Amount: <b>{amount} ETB</b>\n"
            "Method: <b>{method}</b>\n"
            "Status: Pending approval\n\n"
            "You’ll be notified when it is processed."
        ),
        "withdraw.cancelled": "Withdrawal cancelled.",
        "withdraw.pending_cancelled": (
            "<b>Withdrawal cancelled</b>\n\n"
            "Your pending request was cancelled. You can submit a new one."
        ),
        "withdraw.min": "Minimum withdrawal is 100 ETB.",
        "withdraw.insufficient": "Insufficient balance.\n\nAvailable: {balance} ETB",
        "withdraw.expired": "Withdrawal session expired.",
        "withdraw.pending_missing": "Pending withdrawal not found.",
        "withdraw.decision.approved": (
            "<b>BRIGHT GAMES</b>\n\n"
            "✅ <b>Withdrawal approved</b>\n\n"
            "Amount: <b>{amount} ETB</b>\n"
            "Request: <code>{ref}</code>\n\n"
            "Your withdrawal was approved and processed.\n"
            "Current balance: <b>{balance} ETB</b>"
        ),
        "withdraw.decision.rejected": (
            "<b>BRIGHT GAMES</b>\n\n"
            "❌ <b>Withdrawal rejected</b>\n\n"
            "Amount: <b>{amount} ETB</b>\n"
            "Request: <code>{ref}</code>\n"
            "Reason: {reason}\n\n"
            "No funds were taken from your wallet. Your balance is unchanged."
        ),
        "withdraw.decision.no_reason": "No reason provided",
        "method.telebirr": "Telebirr",
        "method.cbe": "CBE",
        "method.cbebirr": "CBE Birr",
        "method.boa": "Bank of Abyssinia",
        "deposit.title.telebirr": "Telebirr Deposit",
        "deposit.title.cbe": "CBE Deposit",
        "deposit.title.cbebirr": "CBE Birr Deposit",
        "deposit.title.boa": "Bank of Abyssinia Deposit",
        "choose_menu": "Please choose an option from the menu.",
        "username.not_set": "Not set",
    },
    "am": {
        "cmd.start": "እንኳን ደህና መጡ እና ዋና ምናሌ",
        "cmd.play": "የጨዋታዎች ምናሌን ክፈት",
        "cmd.games": "ሁሉንም ጨዋታዎች ይመልከቱ",
        "cmd.bingo": "ቢንጎ ይጫወቱ",
        "cmd.dama": "ዳማ ይጫወቱ",
        "cmd.aviator": "አቪየተር ይጫወቱ",
        "cmd.plinko": "ፕሊንኮ ይጫወቱ",
        "cmd.lotto": "ሎቶ ስፒን ይጫወቱ",
        "cmd.balance": "የኪስ ቦርሳ ቀሪ ገንዘብ ይመልከቱ",
        "cmd.language": "እንግሊዝኛ / አማርኛ ቀይር",
        "cmd.help": "ቦቱን እንዴት መጠቀም እንደሚቻል",
        "cmd.deposit": "ገንዘብ አስገባ",
        "cmd.withdraw": "ገንዘብ አውጣ",
        "cmd.invite": "ጓደኞችን ጋብዝ",
        "btn.play_games": "ጨዋታዎች",
        "btn.play": "መተግበሪያ ክፈት",
        "btn.play_bingo": "ቢንጎ ጫወት",
        "btn.play_dama": "ዳማ ጫወት",
        "btn.play_aviator": "አቪየተር ጫወት",
        "btn.play_plinko": "ፕሊንኮ ጫወት",
        "btn.play_lotto": "ሎቶ ጫወት",
        "btn.balance": "ቀሪ ገንዘብ",
        "btn.deposit": "አስገባ",
        "btn.withdraw": "አውጣ",
        "btn.transfer": "አስተላልፍ",
        "btn.register": "ተመዝገብ",
        "btn.invite": "ጋብዝ",
        "btn.help": "እገዛ",
        "btn.language": "ቋንቋ",
        "btn.support": "ድጋፍ",
        "btn.home": "መነሻ",
        "btn.back": "ተመለስ",
        "btn.paid": "ከፍያለሁ",
        "btn.confirm": "አረጋግጥ",
        "btn.cancel": "ሰርዝ",
        "btn.lang_en": "English",
        "btn.lang_am": "አማርኛ",
        "btn.contact_support": "ድጋፍ አነጋግር",
        "btn.cancel_pending_withdraw": "በመጠባበቅ ላይ ያለውን ሰርዝ",
        "welcome": (
            "<b>እንኳን ደህና መጡ፣ {name}!</b>\n\n"
            "<b>BRIGHT GAMES</b>\n"
            "ቢንጎ · ዳማ · አቪየተር · ፕሊንኮ · ሎቶ\n\n"
            "{referral}"
            "ለመጀመር ከታች ያለውን አማራጭ ይምረጡ።"
        ),
        "welcome.referral": (
            "<b>በግብዣ ሊንክ መጡ!</b>\n"
            "የእንኳን ደህና መጣችሁ ቦነስ ለማግኘት ይመዝገቡ።\n\n"
        ),
        "menu.home": "<b>ዋና ምናሌ</b>\n\nBRIGHT GAMES — አማራጭ ይምረጡ፦",
        "menu.games": (
            "<b>ጨዋታዎች</b>\n\n"
            "ጨዋታውን በቀጥታ በሚኒ አፕ ውስጥ ይክፈቱ፦"
        ),
        "game.bingo.blurb": "ክላሲክ የኢትዮጵያ ቢንጎ",
        "game.dama.blurb": "የኢትዮጵያ ዳማ — በመስመር ላይ",
        "game.aviator.blurb": "ከመውደቁ በፊት ያውጡ",
        "game.plinko.blurb": "ኳሱን ጣሉ፣ ማባዣዎችን ይምቱ",
        "game.lotto.blurb": "ለጋራ ሽልማት ይሽከረከሩ",
        "open.game": (
            "<b>{title}</b>\n\n"
            "{blurb}\n\n"
            "ሚኒ አፑን ለመክፈት ከታች ይጫኑ።"
        ),
        "language.prompt": (
            "<b>ቋንቋ</b>\n\n"
            "አሁን፦ <b>{current}</b>\n\n"
            "English ወይም አማርኛ ይምረጡ።"
        ),
        "language.changed": "ቋንቋ ወደ <b>{label}</b> ተቀይሯል።",
        "language.label.en": "English",
        "language.label.am": "አማርኛ",
        "help": (
            "<b>እገዛ — BRIGHT GAMES</b>\n\n"
            "<b>ትዕዛዞች</b>\n"
            "/start — ዋና ምናሌ\n"
            "/play ወይም /games — የጨዋታ ዝርዝር\n"
            "/bingo /dama /aviator /plinko /lotto — ጨዋታ ክፈት\n"
            "/balance — ቀሪ ገንዘብ\n"
            "/language — እንግሊዝኛ ወይም አማርኛ\n"
            "/help — ይህ መልእክት\n\n"
            "<b>መጀመር</b>\n"
            "1. መለያዎን ይመዝገቡ\n"
            "2. ወደ ኪስ ቦርሳዎ ገንዘብ ያስገቡ\n"
            "3. ከምናሌው ጨዋታ ይክፈቱ\n\n"
            "ዝቅተኛ ተቀማጭ፦ <b>10 ብር</b>\n"
            "ዝቅተኛ ማውጫ፦ <b>100 ብር</b>"
        ),
        "balance": (
            "<b>የእርስዎ ቀሪ ገንዘብ</b>\n\n"
            "<b>{balance} ብር</b>"
            "{pending}"
            "\n\nለመጫወት ዝግጁ ነዎት?"
        ),
        "balance.pending": (
            "\n\n──────────────\n\n"
            "<b>በመጠባበቅ ላይ ያለ ማውጫ</b>\n"
            "መጠን፦ <b>{amount} ብር</b>\n"
            "ዘዴ፦ <b>{method}</b>\n"
            "ሁኔታ፦ <b>{status}</b>"
        ),
        "err.not_registered": "እባክዎ መጀመሪያ ይመዝገቡ።",
        "err.user_not_found": "መለያ አልተገኘም። ለመፍጠር ተመዝገብን ይጫኑ።",
        "err.generic": "የሆነ ችግር ተፈጥሯል። እንደገና ይሞክሩ።",
        "register.already": "አስቀድመው ተመዝግበዋል። መገለጫዎ ዘመናዊ ነው።",
        "register.updated": (
            "<b>መገለጫ ተዘምኗል</b>\n\n"
            "ከቴሌግራም የተመሳሰሉ፦\n\n{fields}"
        ),
        "register.success": (
            "<b>ምዝገባ ተሳክቷል!</b>\n\n"
            "ስም፦ <b>{name}</b>\n"
            "የተጠቃሚ ስም፦ <b>{username}</b>\n"
            "የግብዣ ኮድ፦ <code>{code}</code>\n\n"
            "የእንኳን ደህና መጣችሁ ቦነስ፦ <b>10 ብር</b>"
        ),
        "register.referral_notify": (
            "<b>የግብዣ ቦነስ!</b>\n\n"
            "ጓደኛዎ <b>{name}</b> በሊንክዎ ተመዝግቧል።\n"
            "ተቀብለዋል፦ <b>10 ብር</b>"
        ),
        "invite": (
            "<b>ጓደኞችን ጋብዙ</b>\n\n"
            "ሊንክዎን ያጋሩ፦\n"
            "<code>{link}</code>\n\n"
            "ጓደኛዎ <b>10 ብር</b> ቦነስ ያገኛል።\n"
            "እርስዎ በእያንዳንዱ ምዝገባ <b>10 ብር</b> ያገኛሉ።"
        ),
        "support": (
            "<b>ድጋፍ</b>\n\n"
            "ስለ ተቀማጭ፣ ማውጫ፣ ጨዋታዎች እና መለያ ጉዳዮች እንረዳዎታለን።\n"
            "ድጋፍ ለማነጋገር ከታች ይጫኑ።"
        ),
        "deposit.menu": "<b>ተቀማጭ</b>\n\nየክፍያ ዘዴ ይምረጡ፦",
        "deposit.method": (
            "{title}\n\n"
            "<b>የሂሳብ ስም</b>\n{account_name}\n\n"
            "<b>ሂሳብ / ስልክ</b>\n<code>{account_number}</code>\n\n"
            "<b>ዝቅተኛ</b>\n10 ብር\n\n"
            "<b>ደረጃዎች</b>\n"
            "1. ወደ ከላይ ያለው ሂሳብ ይላኩ።\n"
            "2. የማረጋገጫ ኤስኤምኤስ ያስቀምጡ።\n"
            "3. <b>ከፍያለሁ</b>ን ይጫኑ።\n"
            "4. ኤስኤምኤሱን ወደዚህ ቦት ያስተላልፉ።"
        ),
        "deposit.forward_sms": "አሁን የቴሌብር ማረጋገጫ ኤስኤምኤስ ያስተላልፉ።",
        "deposit.success": (
            "<b>ተቀማጭ ተሳክቷል</b>\n\n"
            "መጠን፦ <b>{amount} ብር</b>\n"
            "ግብይት፦ <code>{tx}</code>\n\n"
            "ቀሪ ገንዘብዎ ተዘምኗል።"
        ),
        "deposit.invalid_sms": "ልክ ያልሆነ ኤስኤምኤስ። ትክክለኛውን ማረጋገጫ ያስተላልፉ።",
        "deposit.tx_not_found": "ግብይት አልተገኘም። ትንሽ ጠብቀው እንደገና ይሞክሩ።",
        "deposit.tx_used": "ይህ ግብይት አስቀድሞ ጥቅም ላይ ውሏል።",
        "transfer.ask_user": "የተቀባዩን የቴሌግራም የተጠቃሚ ስም ያስገቡ።\n\nምሳሌ፦\n@username",
        "transfer.ask_amount": "ተቀባይ ተገኝቷል፦ @{username}\n\nመጠን ያስገቡ፦",
        "transfer.confirm": (
            "<b>ዝውውር አረጋግጥ</b>\n\n"
            "ለ፦ @{username}\n"
            "መጠን፦ <b>{amount} ብር</b>"
        ),
        "transfer.done": (
            "<b>ዝውውር ተጠናቋል</b>\n\n"
            "ተልኳል፦ <b>{amount} ብር</b>\n"
            "ለ፦ @{username}\n"
            "ቀሪ፦ <b>{balance} ብር</b>"
        ),
        "transfer.received": (
            "<b>ዝውውር ተቀብለዋል</b>\n\n"
            "መጠን፦ <b>{amount} ብር</b>\n"
            "ከ፦ @{username}\n"
            "አዲስ ቀሪ፦ <b>{balance} ብር</b>"
        ),
        "transfer.cancelled": "ዝውውር ተሰርዟል።",
        "transfer.expired": "ይህ ዝውውር ጊዜው አልፏል።",
        "transfer.missing": "የዝውውር መረጃ ጠፍቷል። እንደገና ይጀምሩ።",
        "transfer.self": "ለራስዎ ማስተላለፍ አይቻልም።",
        "transfer.not_found": "ተጠቃሚ አልተገኘም።",
        "transfer.invalid_amount": "ልክ ያልሆነ መጠን።",
        "transfer.amount_positive": "መጠኑ ከዜሮ መብለጥ አለበት።",
        "transfer.failed": "ዝውውር አልተሳካም። እንደገና ይሞክሩ።",
        "transfer.insufficient": "በቂ ቀሪ ገንዘብ የለም።",
        "withdraw.select": "<b>የማውጫ ዘዴ ይምረጡ</b>",
        "withdraw.pending": (
            "<b>ማውጫ</b>\n\n"
            "አስቀድመው በመጠባበቅ ላይ ያለ ማውጫ አለዎት።\n\n"
            "መጠን፦ <b>{amount} ብር</b>\n"
            "ዘዴ፦ <b>{method}</b>\n\n"
            "ሌላ ከማስገባትዎ በፊት ይሰርዙ።"
        ),
        "withdraw.ask_name": "የሂሳብ ባለቤቱን ሙሉ ስም ያስገቡ።",
        "withdraw.ask_number": "የሂሳብ / ስልክ ቁጥርዎን ያስገቡ።",
        "withdraw.ask_amount": "የማውጫ መጠን ያስገቡ።\n\nዝቅተኛ፦ <b>100 ብር</b>",
        "withdraw.confirm": (
            "<b>ማውጫ አረጋግጥ</b>\n\n"
            "ዘዴ፦ {method}\n"
            "የሂሳብ ስም፦ {name}\n"
            "የሂሳብ ቁጥር፦ {number}\n"
            "መጠን፦ <b>{amount} ብር</b>"
        ),
        "withdraw.submitted": (
            "<b>የማውጫ ጥያቄ ተልኳል</b>\n\n"
            "መጠን፦ <b>{amount} ብር</b>\n"
            "ዘዴ፦ <b>{method}</b>\n"
            "ሁኔታ፦ በማጽደቅ ላይ\n\n"
            "ሲሰራ ማሳወቂያ ያገኛሉ።"
        ),
        "withdraw.cancelled": "ማውጫ ተሰርዟል።",
        "withdraw.pending_cancelled": (
            "<b>ማውጫ ተሰርዟል</b>\n\n"
            "በመጠባበቅ ላይ ያለው ጥያቄ ተሰርዟል። አዲስ ማስገባት ይችላሉ።"
        ),
        "withdraw.min": "ዝቅተኛ ማውጫ 100 ብር ነው።",
        "withdraw.insufficient": "በቂ ቀሪ ገንዘብ የለም።\n\nያለዎት፦ {balance} ብር",
        "withdraw.expired": "የማውጫ ክፍለ ጊዜ ጊዜው አልፏል።",
        "withdraw.pending_missing": "በመጠባበቅ ላይ ያለ ማውጫ አልተገኘም።",
        "withdraw.decision.approved": (
            "<b>BRIGHT GAMES</b>\n\n"
            "✅ <b>ማውጫ ጸድቋል</b>\n\n"
            "መጠን፦ <b>{amount} ብር</b>\n"
            "ጥያቄ፦ <code>{ref}</code>\n\n"
            "የማውጫ ጥያቄዎ ጸድቆ ተሰርቷል።\n"
            "አሁን ያለዎት ቀሪ ሂሳብ፦ <b>{balance} ብር</b>"
        ),
        "withdraw.decision.rejected": (
            "<b>BRIGHT GAMES</b>\n\n"
            "❌ <b>ማውጫ ውድቅ ሆኗል</b>\n\n"
            "መጠን፦ <b>{amount} ብር</b>\n"
            "ጥያቄ፦ <code>{ref}</code>\n"
            "ምክንያት፦ {reason}\n\n"
            "ከቀሪ ሂሳብዎ ምንም ገንዘብ አልተቀነሰም። ቀሪ ሂሳብዎ አልተለወጠም።"
        ),
        "withdraw.decision.no_reason": "ምክንያት አልተሰጠም",
        "method.telebirr": "ቴሌብር",
        "method.cbe": "ሲቢኢ",
        "method.cbebirr": "ሲቢኢ ብር",
        "method.boa": "አቢሲኒያ ባንክ",
        "deposit.title.telebirr": "ቴሌብር ተቀማጭ",
        "deposit.title.cbe": "ሲቢኢ ተቀማጭ",
        "deposit.title.cbebirr": "ሲቢኢ ብር ተቀማጭ",
        "deposit.title.boa": "አቢሲኒያ ባንክ ተቀማጭ",
        "choose_menu": "እባክዎ ከምናሌው አማራጭ ይምረጡ።",
        "username.not_set": "አልተቀናበረም",
    },
}

COMMAND_KEYS = (
    ("start", "cmd.start"),
    ("play", "cmd.play"),
    ("games", "cmd.games"),
    ("bingo", "cmd.bingo"),
    ("dama", "cmd.dama"),
    ("aviator", "cmd.aviator"),
    ("plinko", "cmd.plinko"),
    ("lotto", "cmd.lotto"),
    ("balance", "cmd.balance"),
    ("language", "cmd.language"),
    ("help", "cmd.help"),
    ("deposit", "cmd.deposit"),
    ("withdraw", "cmd.withdraw"),
    ("invite", "cmd.invite"),
)

GAME_TITLES = {
    "bingo": "Bingo",
    "dama": "Dama",
    "aviator": "Aviator",
    "plinko": "Plinko",
    "lotto": "Lotto Spin",
}


def t(locale: str | None, key: str, **params: Any) -> str:
    lang = normalize_locale(locale) or DEFAULT_LOCALE
    catalog = MESSAGES.get(lang) or MESSAGES[DEFAULT_LOCALE]
    template = catalog.get(key) or MESSAGES[DEFAULT_LOCALE].get(key) or key
    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, ValueError):
        return template
