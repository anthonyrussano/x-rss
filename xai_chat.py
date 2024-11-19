import aiohttp
from typing import List, Dict, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
import logging
from config import CONFIG  # Reuse the CONFIG object from config.py

logger = logging.getLogger(__name__)

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
                "model": "grok-beta",  # Replace with the appropriate model name if needed
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
