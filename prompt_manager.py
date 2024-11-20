from typing import List, Dict

class PromptManager:
    """Manages different types of prompts for content generation."""
    
    @staticmethod
    def get_single_tweet_prompt(article_title: str, article_content: str, url: str) -> List[Dict[str, str]]:
        """Generate prompt for single tweet creation."""
        return [
            {
                "role": "system",
                "content": (
                    "You are an AI assistant specialized in creating viral tweets. "
                    "Create engaging tweets that encourage discussion and sharing. "
                    "Use these strategies:\n"
                    "1. Ask thought-provoking questions\n"
                    "2. Include relevant hashtags (max 2-3)\n"
                    "3. Use emojis strategically\n"
                    "4. Create controversy or debate when appropriate\n"
                    "5. Tag relevant accounts when applicable"
                )
            },
            {
                "role": "user",
                "content": (
                    f"Article Title: {article_title}\n\n"
                    f"Article Content: {article_content}\n\n"
                    f"URL: {url}\n\n"
                    "Create a viral tweet that will maximize engagement. Include the URL."
                )
            }
        ]

    @staticmethod
    def get_thread_prompt(article_title: str, article_content: str, url: str) -> List[Dict[str, str]]:
        """Generate prompt for thread creation."""
        return [
            {
                "role": "system",
                "content": (
                    "You are an AI assistant that creates engaging Twitter threads. "
                    "Transform articles into informative, compelling threads that keep readers engaged. "
                    "Follow these guidelines:\n"
                    "1. Start with a strong hook\n"
                    "2. Break down complex ideas into digestible parts\n"
                    "3. Use clear transitions between tweets\n"
                    "4. Include relevant data points and insights\n"
                    "5. End with a thought-provoking conclusion\n\n"
                    "Format the thread with '---' between tweets. Keep each tweet under 280 characters."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Article Title: {article_title}\n\n"
                    f"Article Content: {article_content}\n\n"
                    f"URL: {url}\n\n"
                    "Create an engaging thread that breaks down this article. "
                    "Start with a hook tweet that includes the URL. "
                    "End with a call-to-action."
                )
            }
        ] 