import os
import json
import random
import time
import logging
import feedparser
import re
from typing import List, Dict, Optional

import requests
from requests_oauthlib import OAuth1Session

def load_credentials():
    """Load Twitter and xAI API credentials from vars.py or environment variables."""
    try:
        import vars
        print("Loading credentials from vars.py")
        return (
            vars.OAUTH_CONSUMER_KEY,
            vars.OAUTH_CONSUMER_SECRET,
            vars.OAUTH_ACCESS_TOKEN,
            vars.OAUTH_ACCESS_TOKEN_SECRET,
            vars.XAI_API_KEY,
        )
    except ImportError:
        print("vars.py not found, attempting to load credentials from environment variables")
        return (
            os.getenv("OAUTH_CONSUMER_KEY"),
            os.getenv("OAUTH_CONSUMER_SECRET"),
            os.getenv("OAUTH_ACCESS_TOKEN"),
            os.getenv("OAUTH_ACCESS_TOKEN_SECRET"),
            os.getenv("XAI_API_KEY"),
        )

def setup_logging() -> logging.Logger:
    """Set up logging to file and console."""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # File handler
    fh = logging.FileHandler('xai_tweet.log', mode='a')
    fh.setLevel(logging.DEBUG)
    fh_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(fh_formatter)
    logger.addHandler(fh)

    # Console handler for ERROR level
    ch = logging.StreamHandler()
    ch.setLevel(logging.ERROR)
    ch_formatter = logging.Formatter('%(levelname)s: %(message)s')
    ch.setFormatter(ch_formatter)
    logger.addHandler(ch)

    return logger

logger = setup_logging()

class XAIChat:
    """Client for interacting with the xAI API."""

    def __init__(self, api_key: str):
        """Initialize XAI Chat client with API key.

        Args:
            api_key (str): The API key for authentication.

        Raises:
            ValueError: If the API key is empty.
        """
        if not api_key:
            raise ValueError("API key cannot be empty")
        self.api_key = api_key
        self.base_url = "https://api.x.ai/v1"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        logger.debug(f"Initialized XAIChat with base URL: {self.base_url}")

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7
    ) -> Optional[str]:
        """Send a chat request to the xAI API.

        Args:
            messages (List[Dict[str, str]]): The conversation messages.
            temperature (float, optional): Sampling temperature. Defaults to 0.7.

        Returns:
            Optional[str]: The assistant's reply or None if an error occurs.
        """
        try:
            data = {
                "messages": messages,
                "model": "grok-beta",
                "temperature": temperature
            }

            logger.debug(f"Making request to {self.base_url}/chat/completions")
            logger.debug(f"Request data: {json.dumps(data, indent=2)}")

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=data
            )

            logger.debug(f"Response status: {response.status_code}")
            logger.debug(f"Response headers: {dict(response.headers)}")

            response.raise_for_status()
            return self._handle_regular_response(response)

        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {str(e)}")
            if e.response is not None:
                logger.error(f"Response text: {e.response.text}")
            return None

    def _handle_regular_response(self, response: requests.Response) -> Optional[str]:
        """Handle a regular (non-streamed) response.

        Args:
            response (requests.Response): The HTTP response object.

        Returns:
            Optional[str]: The assistant's reply or None if parsing fails.
        """
        try:
            result = response.json()
            logger.debug(f"Received response: {json.dumps(result, indent=2)}")
            return result['choices'][0]['message']['content']
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"Error parsing response: {str(e)}")
            return None

def parse_urls_file(file_content):
    """Parse the RSS feed URLs from a file content."""
    urls = []
    for line in file_content.split("\n"):
        if line.startswith("http") and not line.startswith("#"):
            url = line.split()[0]
            urls.append(url)
    return urls

def get_random_feed(urls):
    """Select a random feed URL from the list."""
    return random.choice(urls)

def fetch_latest_content(feed_url):
    """Fetch the latest content from the RSS feed."""
    feed = feedparser.parse(feed_url)
    if feed.entries:
        latest_entry = feed.entries[0]
        title = latest_entry.title

        # Try to get content from various possible fields
        content = (
            latest_entry.get("content", [{"value": ""}])[0].get("value")
            or latest_entry.get("summary")
            or latest_entry.get("description")
            or ""
        )

        # If content is still empty, try to get it from content:encoded
        if not content and "content_encoded" in latest_entry:
            content = latest_entry.content_encoded

        link = latest_entry.link
        return title, content, link
    return None, None, None

def clean_text(text):
    """Clean the text by removing HTML tags."""
    clean = re.sub("<[^<]+?>", "", text)
    return clean

def exponential_backoff_retry(request_func, max_retries=5):
    """Retry a request with exponential backoff in case of rate limiting."""
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

def post_tweet(tweet_text, oauth_session):
    """Post a single tweet using the Twitter API."""
    max_tweet_length = 280
    if len(tweet_text) > max_tweet_length:
        tweet_text = tweet_text[:max_tweet_length - 3] + "..."

    payload = {"text": tweet_text}

    # Wrap the API call in a retry logic function
    response = exponential_backoff_retry(
        lambda: oauth_session.post("https://api.twitter.com/2/tweets", json=payload)
    )
    if response and response.status_code == 201:
        print(f"Posted tweet: {tweet_text}")
    else:
        print("Failed to post tweet.")

def main():
    # Load credentials
    (
        consumer_key,
        consumer_secret,
        access_token,
        access_token_secret,
        xai_api_key,
    ) = load_credentials()

    if not all([consumer_key, consumer_secret, access_token, access_token_secret]):
        raise ValueError(
            "Twitter OAuth credentials are not set in vars.py or environment variables."
        )

    if not xai_api_key:
        raise ValueError(
            "xAI API key is not set in vars.py or environment variables."
        )

    # Initialize Twitter OAuth session
    oauth = OAuth1Session(
        consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=access_token,
        resource_owner_secret=access_token_secret,
    )

    # Initialize xAI Chat client
    chat_client = XAIChat(xai_api_key)

    # Parse the rss file
    with open("rss", "r") as file:
        urls_content = file.read()
    urls = parse_urls_file(urls_content)

    # Get a random feed
    random_feed = get_random_feed(urls)

    # Fetch the latest content
    title, content, url = fetch_latest_content(random_feed)

    if title and content and url:
        # Clean the content
        cleaned_content = clean_text(content)

        # Prepare the messages for xAI API
        messages = [
            {
                "role": "system",
                "content": "You are an AI assistant that creates engaging tweets summarizing articles. Craft a tweet based on the provided content and include the URL."
            },
            {
                "role": "user",
                "content": f"Article Title: {title}\n\nArticle Content: {cleaned_content}\n\nURL: {url}\n\nPlease write a tweet summarizing this article and include the URL."
            }
        ]

        # Get the tweet text from Grok
        tweet_text = chat_client.chat(messages, temperature=0.7)

        if tweet_text:
            # Post the tweet
            post_tweet(tweet_text, oauth)
        else:
            print("Failed to generate tweet from Grok.")
    else:
        print("No content found to tweet.")

if __name__ == "__main__":
    main()
