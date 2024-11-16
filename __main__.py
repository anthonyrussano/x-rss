import json
import random
import time
from requests_oauthlib import OAuth1Session
import os
import feedparser
import re


def parse_urls_file(file_content):
    urls = []
    for line in file_content.split("\n"):
        if line.startswith("http") and not line.startswith("#"):
            url = line.split()[0]
            urls.append(url)
    return urls


def get_random_feed(urls):
    return random.choice(urls)


def fetch_latest_content(feed_url):
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
    # Remove HTML tags
    clean = re.sub("<[^<]+?>", "", text)
    return clean


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


def post_tweet_thread(title, content, url, oauth_session):
    base_tweet_text = f"{title}\nRead more: {url}"
    max_tweet_length = 280
    max_tweets = 3  # Maximum number of tweets in the thread
    tweets = []

    # First tweet with title and URL
    tweets.append(base_tweet_text)

    # Split content into subsequent tweets
    remaining_tweets = max_tweets - 1  # We've already used one tweet for the title/URL
    while len(content) > 0 and remaining_tweets > 0:
        if len(content) <= max_tweet_length:
            tweets.append(content)
            content = ""
        else:
            split_point = content.rfind(" ", 0, max_tweet_length)
            if split_point == -1:
                split_point = max_tweet_length
            tweets.append(content[:split_point])
            content = content[split_point:].strip()
        remaining_tweets -= 1

    # If there's still content left, add an ellipsis to the last tweet
    if content and len(tweets) == max_tweets:
        last_tweet = tweets[-1]
        tweets[-1] = last_tweet[: max_tweet_length - 3] + "..."

    previous_tweet_id = None
    for tweet_text in tweets:
        payload = {"text": tweet_text}
        if previous_tweet_id:
            payload["reply"] = {"in_reply_to_tweet_id": previous_tweet_id}

        # Wrap the API call in a retry logic function
        response = exponential_backoff_retry(
            lambda: oauth_session.post("https://api.twitter.com/2/tweets", json=payload)
        )
        if response and response.status_code == 201:
            response_data = response.json()
            previous_tweet_id = response_data["data"]["id"]
            print(f"Posted tweet: {tweet_text[:50]}...")
        else:
            print("Failed to post tweet.")
            break


# Credential loading
def load_credentials():
    try:
        import vars

        print("Loading credentials from vars.py")
        return (
            vars.OAUTH_CONSUMER_KEY,
            vars.OAUTH_CONSUMER_SECRET,
            vars.OAUTH_ACCESS_TOKEN,
            vars.OAUTH_ACCESS_TOKEN_SECRET,
        )
    except ImportError:
        print(
            "vars.py not found, attempting to load credentials from environment variables"
        )
        return (
            os.getenv("OAUTH_CONSUMER_KEY"),
            os.getenv("OAUTH_CONSUMER_SECRET"),
            os.getenv("OAUTH_ACCESS_TOKEN"),
            os.getenv("OAUTH_ACCESS_TOKEN_SECRET"),
        )


# Load credentials
consumer_key, consumer_secret, access_token, access_token_secret = load_credentials()

if not all([consumer_key, consumer_secret, access_token, access_token_secret]):
    raise ValueError(
        "Twitter OAuth credentials are not set in vars.py or environment variables."
    )

oauth = OAuth1Session(
    consumer_key,
    client_secret=consumer_secret,
    resource_owner_key=access_token,
    resource_owner_secret=access_token_secret,
)

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

    # Post the tweet thread
    post_tweet_thread(title, cleaned_content, url, oauth)
else:
    print("No content found to tweet.")
