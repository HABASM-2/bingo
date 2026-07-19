"""Public-facing dummy first names for Bingo house-bot win ceremonies.

The bot's DB identity (username / first_name / is_bot) is never changed.
Player-facing winner payloads substitute a stable pick from this list so
the win splash looks like a normal Telegram player.
"""

from __future__ import annotations

import hashlib

# ~100 plausible Telegram-style first names (Ethiopian + international mix).
DUMMY_FIRST_NAMES: tuple[str, ...] = (
    "Abebe",
    "Abel",
    "Abigail",
    "Abrham",
    "Adam",
    "Addis",
    "Alem",
    "Alex",
    "Aman",
    "Amanuel",
    "Amir",
    "Anna",
    "Aster",
    "Aya",
    "Ayana",
    "Bekele",
    "Belen",
    "Ben",
    "Bereket",
    "Betty",
    "Biruk",
    "Brook",
    "Caleb",
    "Chala",
    "Daniel",
    "Dawit",
    "Deborah",
    "Elias",
    "Emebet",
    "Eyasu",
    "Ezra",
    "Fana",
    "Fasika",
    "Feben",
    "Feven",
    "Fikir",
    "Gabriel",
    "Gelila",
    "Getachew",
    "Hana",
    "Helen",
    "Henok",
    "Hiwot",
    "Ibssa",
    "Isaac",
    "Ismael",
    "Jember",
    "Jonathan",
    "Kaleb",
    "Kalkidan",
    "Kidist",
    "Kidus",
    "Lidiya",
    "Liya",
    "Lulit",
    "Mahlet",
    "Marta",
    "Mary",
    "Mekdes",
    "Meklit",
    "Melaku",
    "Meron",
    "Meseret",
    "Michael",
    "Miki",
    "Mimi",
    "Nahom",
    "Naomi",
    "Natnael",
    "Netsanet",
    "Noah",
    "Rahel",
    "Rediet",
    "Robel",
    "Ruth",
    "Saba",
    "Samson",
    "Samuel",
    "Sara",
    "Selam",
    "Semira",
    "Senait",
    "Sisay",
    "Sofia",
    "Soliana",
    "Solomon",
    "Tadesse",
    "Tewodros",
    "Tigist",
    "Tilahun",
    "Timnit",
    "Tsion",
    "Yared",
    "Yabets",
    "Yonas",
    "Yordanos",
    "Yosef",
    "Zelalem",
    "Zewditu",
    "Zion",
)


def pick_dummy_name(round_id: str, bot_user_id: str) -> str:
    """Stable first-name pick for one win announcement (same round + bot)."""

    seed = f"{round_id}:{bot_user_id}".encode()
    digest = hashlib.sha256(seed).hexdigest()
    idx = int(digest, 16) % len(DUMMY_FIRST_NAMES)
    return DUMMY_FIRST_NAMES[idx]


def label5(name: str) -> str:
    """Compact board label: first 5 letters of the display name."""

    letters = "".join(ch for ch in (name or "") if ch.isalpha())
    if letters:
        return letters[:5]
    stripped = (name or "").strip()
    return stripped[:5] if stripped else "?"


def pick_unused_dummy(round_id: str, salt: str | int, used: set[str]) -> str:
    """Pick a dummy name not already in ``used`` (stable start from round+salt).

    Walks the pool from a hash seed so each bot-held number gets a distinct
    public label within the round. If the ~100-name pool is exhausted, appends
    a numeric suffix.
    """

    seed = f"{round_id}:{salt}".encode()
    digest = hashlib.sha256(seed).hexdigest()
    start = int(digest, 16) % len(DUMMY_FIRST_NAMES)
    for offset in range(len(DUMMY_FIRST_NAMES)):
        name = DUMMY_FIRST_NAMES[(start + offset) % len(DUMMY_FIRST_NAMES)]
        if name not in used:
            return name
    return f"{DUMMY_FIRST_NAMES[start]}{salt}"
