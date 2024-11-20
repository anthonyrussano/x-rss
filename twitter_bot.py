from requests_oauthlib import OAuth1Session
import logging
import asyncio
from typing import List
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)

@dataclass
class ThreadPart:
    text: str
    media_id: str = None
    reply_to_id: str = None

class TwitterBot:
    def __init__(self, oauth_session: OAuth1Session):
        self.oauth = oauth_session

    def _exponential_backoff_retry(self, request_func, max_retries=5):
        """Execute request with exponential backoff retry logic."""
        retry_delay = 10  # start with 10 seconds delay
        for attempt in range(max_retries):
            response = request_func()
            if response.status_code == 201:
                return response
            elif response.status_code == 429:
                logger.warning(f"Rate limit exceeded, retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # double the delay for the next attempt
            else:
                logger.error(f"Failed to post tweet with status {response.status_code}: {response.text}")
                break
        return None

    async def post_tweet(self, tweet_text: str) -> bool:
        """Post a single tweet with retry logic."""
        try:
            response = self._exponential_backoff_retry(
                lambda: self.oauth.post(
                    "https://api.twitter.com/2/tweets",
                    json={"text": tweet_text}
                )
            )
            return response is not None and response.status_code == 201
        except Exception as e:
            logger.error(f"Error posting tweet: {str(e)}")
            return False

    async def post_thread(self, thread_parts: List[ThreadPart]) -> bool:
        """Post a thread of tweets with retry logic."""
        previous_tweet_id = None
        
        try:
            for part in thread_parts:
                payload = {"text": part.text}
                if previous_tweet_id:
                    payload["reply"] = {"in_reply_to_tweet_id": previous_tweet_id}
                
                response = self._exponential_backoff_retry(
                    lambda: self.oauth.post(
                        "https://api.twitter.com/2/tweets",
                        json=payload
                    )
                )
                
                if not response or response.status_code != 201:
                    return False
                
                response_data = response.json()
                previous_tweet_id = response_data["data"]["id"]
                logger.info(f"Posted tweet part: {part.text[:50]}...")
                
                # Add small delay between tweets to avoid rate limits
                await asyncio.sleep(CONFIG["thread_delay_seconds"])
            
            return True
            
        except Exception as e:
            logger.error(f"Error posting thread: {str(e)}")
            return False
