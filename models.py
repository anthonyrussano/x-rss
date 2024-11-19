from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib

@dataclass
class Article:
    title: str
    content: str
    url: str
    published_date: datetime
    feed_id: str

    def is_recent(self, hours: int) -> bool:
        return datetime.now() - self.published_date < timedelta(hours=hours)

    def get_hash(self) -> str:
        return hashlib.md5(f"{self.url}{self.title}".encode()).hexdigest()
