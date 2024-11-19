from requests_oauthlib import OAuth1Session
import logging

logger = logging.getLogger(__name__)

class TwitterBot:
    def __init__(self, oauth_session: OAuth1Session):
        self.oauth = oauth_session

    async def post_tweet(self, tweet_text: str) -> bool:
        """Post a tweet asynchronously."""
        url = "https://api.twitter.com/2/tweets"
        payload = {"text": tweet_text}

        try:
            response = self.oauth.post(url, json=payload)
            if response.status_code == 201:
                logger.info("Successfully posted tweet: %s", tweet_text)
                return True
            else:
                logger.error("Failed to post tweet: %s", response.text)
                return False
        except Exception as e:
            logger.error("Error posting tweet: %s", e)
            raise
