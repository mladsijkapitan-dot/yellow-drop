import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
DATABASE_URL: str = os.environ["DATABASE_URL"]
ADMIN_IDS: list[int] = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x]

DROP_COOLDOWN_HOURS: int = 8
DROP_MAX_PER_DAY: int = 3
TRADE_EXPIRE_HOURS: int = 24
TRADE_MAX_ACTIVE: int = 5

RARITY_WEIGHTS: dict[str, float] = {
    "base": 65.0,
    "medium": 25.0,
    "archive": 2.0,
    "legendary": 8.0,
}

RARITY_PRESTIGE: dict[str, int] = {
    "base": 10,
    "medium": 25,
    "archive": 300,
    "legendary": 80,
}
