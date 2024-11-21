from dataclasses import dataclass
from typing import List
import re

@dataclass
class ThreadPart:
    text: str
    media_id: str = None
    reply_to_id: str = None

class ThreadGenerator:
    def __init__(self, max_tweet_length: int = 280):
        self.max_tweet_length = max_tweet_length

    def create_thread(self, title: str, content: str, url: str) -> List[ThreadPart]:
        """Generate an engaging thread from article content."""
        thread = []
        
        # First tweet: Hook + Title
        hook = self._create_hook(title)
        first_tweet = f"{hook}\n\n{url}"
        thread.append(ThreadPart(text=first_tweet))
        
        # Process content into thread parts
        paragraphs = self._split_into_paragraphs(content)
        for paragraph in paragraphs:
            tweet_parts = self._split_into_tweets(paragraph)
            for part in tweet_parts:
                if part.strip():
                    thread.append(ThreadPart(text=part))
        
        # Add final call-to-action tweet
        cta = self._create_cta(url)
        thread.append(ThreadPart(text=cta))
        
        return thread

    def _create_hook(self, title: str) -> str:
        """Create an engaging hook from the title."""
        # Remove any existing emojis to add our own
        title = re.sub(r'[\U0001F300-\U0001F9FF]', '', title)
        return f"🧵 {title}"

    def _create_cta(self, url: str) -> str:
        """Create a call-to-action final tweet."""
        return (
            "💡 Want to learn more?\n\n"
            f"Read the full article here: {url}\n\n"
            "🔄 RT & ❤️ if you found this thread helpful!\n"
            "#Tech #Innovation"
        )

    def _split_into_paragraphs(self, content: str) -> List[str]:
        """Split content into logical paragraphs."""
        # Remove HTML tags and split by double newlines
        clean_content = re.sub(r'<[^>]+>', '', content)
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', clean_content) if p.strip()]
        return paragraphs

    def _split_into_tweets(self, text: str) -> List[str]:
        """Split text into tweet-sized chunks."""
        tweets = []
        while text:
            if len(text) <= self.max_tweet_length:
                tweets.append(text)
                break
            
            # Find the last space within the limit
            split_point = text.rfind(' ', 0, self.max_tweet_length - 5)
            if split_point == -1:
                split_point = self.max_tweet_length - 5
            
            # Add continuation marker
            tweets.append(text[:split_point] + "...")
            text = text[split_point:].strip()
            
            # Add continuation marker at the start of next tweet
            if text:
                text = "..." + text
        
        return tweets 

    def parse_ai_response(self, ai_response: str) -> List[ThreadPart]:
        """Parse the AI-generated thread response into ThreadParts."""
        # Split the response into individual tweets
        tweet_texts = [t.strip() for t in ai_response.split('---') if t.strip()]
        
        # Convert to ThreadParts
        thread_parts = []
        for text in tweet_texts:
            # Ensure tweet meets length requirements
            if len(text) > self.max_tweet_length:
                # Split long tweets if necessary
                parts = self._split_into_tweets(text)
                thread_parts.extend([ThreadPart(text=p) for p in parts])
            else:
                thread_parts.append(ThreadPart(text=text))
        
        return thread_parts 