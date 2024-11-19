import yaml
from pathlib import Path

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
