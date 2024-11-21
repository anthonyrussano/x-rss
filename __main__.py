import asyncio
import logging
from config import CONFIG
from credentials import Credentials
from history import PostHistory
from rss_manager import RSSFeedManager
from twitter_bot import TwitterBot
from models import Article
from xai_chat import XAIChat  # Assuming a separate module for the XAIChat logic
from prompt_manager import PromptManager
from thread_generator import ThreadGenerator

from requests_oauthlib import OAuth1Session
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Default; overridden by CONFIG['log_level'] later
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("twitter_bot.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


async def process_feed(
    feed_url: str,
    rss_manager: RSSFeedManager,
    chat_client: XAIChat,
    twitter_bot: TwitterBot,
    post_history: PostHistory,
) -> bool:
    """Process a single feed to find and tweet a suitable article."""
    try:
        articles = await rss_manager.fetch_feed(feed_url)
        prompt_manager = PromptManager()
        thread_generator = ThreadGenerator()
        
        for article in articles:
            if article.is_recent(CONFIG["article_freshness_hours"]) and not post_history.is_posted(article):
                # Determine if content should be a thread based on length and complexity
                should_thread = _should_create_thread(article.content)
                
                if should_thread:
                    # Generate thread content
                    thread_content = await chat_client.chat(
                        prompt_manager.get_thread_prompt(
                            article.title,
                            article.content,
                            article.url
                        )
                    )
                    
                    if thread_content:
                        # Parse the AI response into thread parts
                        thread_parts = thread_generator.parse_ai_response(thread_content)
                        if await twitter_bot.post_thread(thread_parts):
                            await post_history.add_posted(article)
                            logger.info(f"Successfully posted thread for article: {article.title}")
                            return True
                else:
                    # Generate single tweet
                    tweet_text = await chat_client.chat(
                        prompt_manager.get_single_tweet_prompt(
                            article.title,
                            article.content,
                            article.url
                        )
                    )
                    
                    if tweet_text and await twitter_bot.post_tweet(tweet_text):
                        await post_history.add_posted(article)
                        logger.info(f"Successfully posted tweet for article: {article.title}")
                        return True
        
        return False

    except Exception as e:
        logger.error(f"Error processing feed {feed_url}: {str(e)}")
        return False

def _should_create_thread(content: str) -> bool:
    """Determine if content should be a thread based on length and complexity."""
    # Basic heuristic - can be expanded based on your needs
    word_count = len(content.split())
    has_complex_content = any(indicator in content.lower() for indicator in [
        "research",
        "study",
        "analysis",
        "findings",
        "methodology",
        "results show",
        "according to"
    ])
    
    return word_count > 100 or has_complex_content

def exponential_backoff_retry(request_func, max_retries=5):
    retry_delay = 10  # start with 10 seconds delay
    for attempt in range(max_retries):
        response = request_func()
        if response.status_code == 201:
            return response
        elif response.status_code == 429:
            print(f"Rate limit exceeded, retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
            retry_delay *= 2  # double the delay for the next attempt
        else:
            print(
                f"Failed to post tweet with status {response.status_code}: {response.text}"
            )
            break
    return None

async def main():
    """Main entry point for the Twitter bot."""
    logger.info("Starting RSS feed processing...")
    # Update log level from config
    logger.setLevel(getattr(logging, CONFIG["log_level"], logging.INFO))

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
        await post_history.cleanup_old_entries(days=CONFIG["history_retention_days"])

        # Get all feeds in random order
        feeds = rss_manager.get_random_feeds(count=len(rss_manager.feeds))
        logger.info(f"Loaded {len(feeds)} feeds for processing.")

        # Process feeds until a tweet is posted
        for feed_url in feeds:
            logger.info(f"Processing feed: {feed_url}")
            tweet_posted = await process_feed(
                feed_url,
                rss_manager,
                chat_client,
                twitter_bot,
                post_history,
            )
            if tweet_posted:
                logger.info("Successfully posted one tweet, finishing process.")
                break
        else:
            logger.warning("No suitable articles found across all feeds.")

    except Exception as e:
        logger.error(f"Error in main process: {str(e)}", exc_info=True)
    finally:
        if "rss_manager" in locals():
            logger.info("Closing RSS manager...")
            await rss_manager.close()
            logger.info("RSS manager closed")


if __name__ == "__main__":
    asyncio.run(main())
