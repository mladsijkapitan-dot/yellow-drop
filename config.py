import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
DATABASE_URL: str = os.environ["DATABASE_URL"]
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379")

DROP_COOLDOWN_HOURS: int = 8
DROP_MAX_PER_DAY: int = 3
TRADE_EXPIRE_HOURS: int = 24
TRADE_MAX_ACTIVE: int = 5

RARITY_WEIGHTS: dict[str, float] = {
    "base": 60.0,
    "medium": 28.0,
    "archive": 10.0,
    "legendary": 2.0,
}
