import feedparser
import aiohttp
from random import sample
from urllib.parse import urlparse
from typing import Optional, List
import logging
import asyncio
from datetime import datetime
from models import Article

logger = logging.getLogger(__name__)

class RSSFeedManager:
    def __init__(self, rss_file: str = "rss"):
        self.rss_file = rss_file
        self.feeds = self._load_feeds()
        self._session: Optional[aiohttp.ClientSession] = None

    def _load_feeds(self) -> List[str]:
        """Load RSS feeds from the RSS file."""
        try:
            with open(self.rss_file) as f:
                feeds = [
                    line.split()[0].strip()  # Take only the first part (URL) of each line
                    for line in f
                    if line.strip() and urlparse(line.split()[0].strip()).scheme in ["http", "https"]
                ]
            if not feeds:
                raise ValueError("No valid feeds found in the RSS file.")
            logger.info(f"Loaded {len(feeds)} feeds.")
            return feeds
        except FileNotFoundError:
            logger.error(f"RSS file not found: {self.rss_file}")
            raise
        except Exception as e:
            logger.error(f"Error loading feeds: {e}")
            raise


    async def _ensure_session(self):
        """Ensure that the aiohttp session is initialized."""
        if self._session is None:
            headers = {
                "User-Agent": "RSSFeedManager/1.0",
            }
            self._session = aiohttp.ClientSession(headers=headers)

    async def fetch_feed(self, feed_url: str) -> List[Article]:
        """Fetch and parse the RSS feed."""
        await self._ensure_session()
        try:
            async with self._session.get(feed_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                response.raise_for_status()
                feed_content = await response.text()

            parsed_feed = feedparser.parse(feed_content)
            if not parsed_feed.entries:
                logger.warning(f"No entries found in feed: {feed_url}")
                return []

            articles = []
            for entry in parsed_feed.entries:
                published = entry.get("published_parsed") or entry.get("updated_parsed")
                published_date = datetime(*published[:6]) if published else datetime.now()

                articles.append(Article(
                    title=entry.get("title", ""),
                    url=entry.get("link", ""),
                    content=(
                        entry.get("summary", "")
                        or entry.get("description", "")
                        or ""
                    ),
                    published_date=published_date,
                    feed_id=feed_url,
                ))

            logger.info(f"Fetched {len(articles)} articles from {feed_url}.")
            return articles
        except Exception as e:
            logger.error(f"Error fetching feed {feed_url}: {e}")
            return []

    async def close(self):
        """Close the aiohttp session."""
        if self._session:
            await self._session.close()
            self._session = None

    def get_random_feeds(self, count: int = 1) -> List[str]:
        """Get a random selection of feed URLs."""
        if not self.feeds:
            raise ValueError("No feeds available to select.")
        return sample(self.feeds, min(count, len(self.feeds)))
