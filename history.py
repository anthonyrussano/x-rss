import json
from pathlib import Path
from datetime import datetime, timedelta
import asyncio

class PostHistory:
    def __init__(self, history_file: str = "posted_articles.json"):
        self.history_file = Path(history_file)
        self.posted_articles = self._load_history()
        self._lock = asyncio.Lock()

    def _load_history(self) -> dict:
        if self.history_file.exists():
            with open(self.history_file) as f:
                history = json.load(f)
                return {k: datetime.fromisoformat(v) for k, v in history.items()}
        return {}

    async def _save_history(self) -> None:
        async with self._lock:
            with open(self.history_file, 'w') as f:
                history = {k: v.isoformat() for k, v in self.posted_articles.items()}
                json.dump(history, f, indent=2)

    def is_posted(self, article) -> bool:
        return article.get_hash() in self.posted_articles

    async def add_posted(self, article) -> None:
        self.posted_articles[article.get_hash()] = datetime.now()
        await self._save_history()

    async def cleanup_old_entries(self, days: int) -> None:
        cutoff = datetime.now() - timedelta(days=days)
        self.posted_articles = {
            k: v for k, v in self.posted_articles.items()
            if v > cutoff
        }
        await self._save_history()
