import os
import json
import random
import time
import logging
import feedparser
import re
from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
import hashlib
from urllib.parse import urlparse
import asyncio
import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential
import yaml
from functools import partial
from requests_oauthlib import OAuth1Session

# Add this right after the imports at the top of the file
logging.basicConfig(
    level=logging.INFO,  # This will be overridden by CONFIG['log_level'] later
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('twitter_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load configuration
def load_config() -> dict:
    """Load configuration from YAML file."""
    config_path = Path("config.yaml")
    if not config_path.exists():
        return {
            "max_retries": 3,
            "retry_multiplier": 1,
            "min_retry_wait": 4,
            "max_retry_wait": 10,
            "history_retention_days": 30,
            "article_freshness_hours": 24,
            "max_feeds_per_run": 25,
            "max_articles_per_feed": 5,
            "log_level": "INFO"
        }
    
    with open(config_path) as f:
        return yaml.safe_load(f)

CONFIG = load_config()

@dataclass
class Credentials:
    """Data class to store API credentials."""
    oauth_consumer_key: str
    oauth_consumer_secret: str
    oauth_access_token: str
    oauth_access_token_secret: str
    xai_api_key: str

    @classmethod
    def load(cls) -> 'Credentials':
        """Load credentials from vars.py or environment variables."""
        try:
            import vars
            print("Loading credentials from vars.py")
            return cls(
                oauth_consumer_key=vars.OAUTH_CONSUMER_KEY,
                oauth_consumer_secret=vars.OAUTH_CONSUMER_SECRET,
                oauth_access_token=vars.OAUTH_ACCESS_TOKEN,
                oauth_access_token_secret=vars.OAUTH_ACCESS_TOKEN_SECRET,
                xai_api_key=vars.XAI_API_KEY,
            )
        except ImportError:
            print("Loading credentials from environment variables")
            return cls(
                oauth_consumer_key=os.getenv("OAUTH_CONSUMER_KEY", ""),
                oauth_consumer_secret=os.getenv("OAUTH_CONSUMER_SECRET", ""),
                oauth_access_token=os.getenv("OAUTH_ACCESS_TOKEN", ""),
                oauth_access_token_secret=os.getenv("OAUTH_ACCESS_TOKEN_SECRET", ""),
                xai_api_key=os.getenv("XAI_API_KEY", ""),
            )

    def validate(self) -> None:
        """Validate that all required credentials are present."""
        missing = [field for field, value in self.__dict__.items() if not value]
        if missing:
            raise ValueError(f"Missing required credentials: {', '.join(missing)}")

@dataclass
class Article:
    """Data class to store article information."""
    title: str
    content: str
    url: str
    published_date: datetime
    feed_id: str

    def is_recent(self, hours: int = CONFIG['article_freshness_hours']) -> bool:
        """Check if the article is recent."""
        return datetime.now() - self.published_date < timedelta(hours=hours)

    def get_hash(self) -> str:
        """Generate a unique hash for the article."""
        return hashlib.md5(f"{self.url}{self.title}".encode()).hexdigest()

class PostHistory:
    """Class to manage posted content history."""
    
    def __init__(self, history_file: str = "posted_articles.json"):
        self.history_file = Path(history_file)
        self.posted_articles = self._load_history()
        self._lock = asyncio.Lock()

    def _load_history(self) -> Dict[str, datetime]:
        """Load posting history from file."""
        if self.history_file.exists():
            with open(self.history_file) as f:
                history = json.load(f)
                return {k: datetime.fromisoformat(v) for k, v in history.items()}
        return {}

    async def _save_history(self) -> None:
        """Save posting history to file."""
        async with self._lock:
            with open(self.history_file, 'w') as f:
                history = {k: v.isoformat() for k, v in self.posted_articles.items()}
                json.dump(history, f, indent=2)

    def is_posted(self, article: Article) -> bool:
        """Check if an article has been posted."""
        return article.get_hash() in self.posted_articles

    async def add_posted(self, article: Article) -> None:
        """Add an article to posting history."""
        self.posted_articles[article.get_hash()] = datetime.now()
        await self._save_history()

    async def cleanup_old_entries(self, days: int = CONFIG['history_retention_days']) -> None:
        """Remove entries older than specified days."""
        cutoff = datetime.now() - timedelta(days=days)
        self.posted_articles = {
            k: v for k, v in self.posted_articles.items()
            if v > cutoff
        }
        await self._save_history()

class XAIChat:
    """Enhanced client for interacting with the xAI API."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("API key cannot be empty")
        self.api_key = api_key
        self.base_url = "https://api.x.ai/v1"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    @retry(
        stop=stop_after_attempt(CONFIG['max_retries']),
        wait=wait_exponential(
            multiplier=CONFIG['retry_multiplier'],
            min=CONFIG['min_retry_wait'],
            max=CONFIG['max_retry_wait']
        )
    )
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7
    ) -> Optional[str]:
        """Send a chat request to the xAI API with retry logic."""
        try:
            data = {
                "messages": messages,
                "model": "grok-beta",
                "temperature": temperature
            }

            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    response.raise_for_status()
                    result = await response.json()
                    return result['choices'][0]['message']['content']

        except Exception as e:
            logger.error(f"Error in chat request: {str(e)}")
            raise

class RSSFeedManager:
    """Class to manage RSS feeds."""
    
    def __init__(self, rss_file: str = "rss"):
        self.rss_file = Path(rss_file)
        self.feeds = self._load_feeds()
        self._session: Optional[aiohttp.ClientSession] = None

    def _load_feeds(self) -> List[str]:
        """Load and validate RSS feeds from file."""
        if not self.rss_file.exists():
            raise FileNotFoundError(f"RSS file not found: {self.rss_file}")
            
        with open(self.rss_file) as f:
            return [
                line.strip().split()[0]
                for line in f
                if line.strip() and line.strip()[0] != "#"
                and urlparse(line.strip().split()[0]).scheme in ['http', 'https']
            ]

    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if self._session is None:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            self._session = aiohttp.ClientSession(headers=headers)

    async def close(self):
        """Close aiohttp session."""
        if self._session:
            await self._session.close()
            self._session = None

    def get_random_feeds(self, count: int = CONFIG['max_feeds_per_run']) -> List[str]:
        """Get a random selection of feed URLs."""
        if not self.feeds:
            raise ValueError("No valid RSS feeds found")
        selected_feeds = random.sample(self.feeds, min(count, len(self.feeds)))
        logger.info(f"Selected {len(selected_feeds)} feeds to process: {selected_feeds}")
        return selected_feeds

    @retry(
        stop=stop_after_attempt(CONFIG['max_retries']),
        wait=wait_exponential(
            multiplier=CONFIG['retry_multiplier'],
            min=CONFIG['min_retry_wait'],
            max=CONFIG['max_retry_wait']
        )
    )
    async def fetch_latest_content(self, feed_url: str) -> List[Article]:
        """Fetch the latest content from an RSS feed with retry logic."""
        try:
            await self._ensure_session()
            async with self._session.get(feed_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                response.raise_for_status()
                feed_content = await response.text()

            feed = feedparser.parse(feed_content)
            if not feed.entries:
                return []

            articles = []
            for entry in feed.entries[:CONFIG['max_articles_per_feed']]:
                content = (
                    entry.get("content", [{"value": ""}])[0].get("value")
                    or entry.get("summary", "")
                    or entry.get("description", "")
                    or entry.get("content_encoded", "")
                )

                published = entry.get('published_parsed') or entry.get('updated_parsed')
                published_date = datetime(*published[:6]) if published else datetime.now()

                articles.append(Article(
                    title=entry.title,
                    content=self._clean_text(content),
                    url=entry.link,
                    published_date=published_date,
                    feed_id=feed_url
                ))

            return articles

        except Exception as e:
            logger.error(f"Error fetching feed {feed_url}: {str(e)}")
            raise

    @staticmethod
    def _clean_text(text: str) -> str:
        """Clean text by removing HTML tags and normalizing whitespace."""
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

class TwitterBot:
    """Class to manage Twitter interactions."""

    def __init__(self, oauth_session: OAuth1Session):
        self.oauth = oauth_session
        self.max_tweet_length = 2500
        self._lock = asyncio.Lock()

    async def post_tweet(self, tweet_text: str) -> bool:
        """Post a tweet asynchronously."""
        payload = {"text": tweet_text}

        # Use lock to prevent concurrent Twitter API calls
        async with self._lock:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                partial(self.oauth.post, "https://api.twitter.com/2/tweets", json=payload)
            )

            if response.status_code != 201:
                logger.error(f"Failed to post tweet: {response.text}")
                raise Exception(f"Tweet posting failed with status {response.status_code}")

            logger.info(f"Successfully posted tweet: {tweet_text[:100]}...")
            return True

async def process_feed(
    feed_url: str,
    rss_manager: RSSFeedManager,
    chat_client: XAIChat,
    twitter_bot: TwitterBot,
    post_history: PostHistory
) -> bool:  # Add return type to indicate if we posted
    """Process a single feed."""
    try:
        articles = await rss_manager.fetch_latest_content(feed_url)
        
        for article in articles:
            if article.is_recent() and not post_history.is_posted(article):
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are an AI assistant that creates engaging tweets. "
                            "Create a tweet that captures the essence of the article "
                            "while maintaining a natural, engaging tone. Include the URL."
                        )
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Article Title: {article.title}\n\n"
                            f"Article Content: {article.content}\n\n"
                            f"URL: {article.url}\n\n"
                            "Please write a tweet summarizing this article and include the URL."
                        )
                    }
                ]

                tweet_text = await chat_client.chat(messages)
                if tweet_text and await twitter_bot.post_tweet(tweet_text):
                    await post_history.add_posted(article)
                    logger.info(f"Successfully posted tweet for article: {article.title}")
                    return True  # Return after first successful tweet
                
        return False

    except Exception as e:
        logger.error(f"Error processing feed {feed_url}: {str(e)}")
        return False

async def main():
    logger.info("Starting RSS feed processing...")
    # Update log level from config
    logger.setLevel(getattr(logging, CONFIG['log_level']))

    try:
        # Load and validate credentials
        logger.info("Loading credentials...")
        credentials = Credentials.load()
        credentials.validate()
        logger.info("Credentials loaded and validated successfully")

        # Initialize components
        logger.info("Initializing components...")
        post_history = PostHistory()
        rss_manager = RSSFeedManager()
        chat_client = XAIChat(credentials.xai_api_key)
        
        oauth = OAuth1Session(
            credentials.oauth_consumer_key,
            client_secret=credentials.oauth_consumer_secret,
            resource_owner_key=credentials.oauth_access_token,
            resource_owner_secret=credentials.oauth_access_token_secret,
        )
        twitter_bot = TwitterBot(oauth)
        logger.info("All components initialized successfully")

        # Clean up old history entries
        logger.info("Cleaning up old history entries...")
        await post_history.cleanup_old_entries()

        # Log RSS file contents
        logger.info("Available feeds:")
        with open("rss") as f:
            logger.info(f.read())

        # Get one random feed
        logger.info("Getting random feed to process...")
        feeds = rss_manager.get_random_feeds(count=1)  # Only get one feed
        logger.info(f"Selected feed to process: {feeds[0]}")
        
        logger.info("Starting to process feed...")
        tweet_posted = await process_feed(
            feeds[0],  # Process only the first feed
            rss_manager,
            chat_client,
            twitter_bot,
            post_history
        )
        
        if tweet_posted:
            logger.info("Successfully posted one tweet, finishing process")
        else:
            logger.info("No suitable articles found to tweet")

    except Exception as e:
        logger.error(f"Error in main process: {str(e)}", exc_info=True)
    finally:
        if 'rss_manager' in locals():
            logger.info("Closing RSS manager...")
            await rss_manager.close()
            logger.info("RSS manager closed")

if __name__ == "__main__":
    asyncio.run(main())