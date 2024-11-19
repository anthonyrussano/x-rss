import os
from dataclasses import dataclass

@dataclass
class Credentials:
    oauth_consumer_key: str
    oauth_consumer_secret: str
    oauth_access_token: str
    oauth_access_token_secret: str
    xai_api_key: str

    @classmethod
    def load(cls) -> 'Credentials':
        """Load credentials from environment variables or a file."""
        try:
            import vars
            return cls(
                oauth_consumer_key=vars.OAUTH_CONSUMER_KEY,
                oauth_consumer_secret=vars.OAUTH_CONSUMER_SECRET,
                oauth_access_token=vars.OAUTH_ACCESS_TOKEN,
                oauth_access_token_secret=vars.OAUTH_ACCESS_TOKEN_SECRET,
                xai_api_key=vars.XAI_API_KEY,
            )
        except ImportError:
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
