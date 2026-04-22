import logging

LOGGER = logging.getLogger("amfi")


def configure_logging() -> None:
    """Configure application logging defaults.

    - Keeps app logs at INFO level
    - Silences noisy HTTP client internals unless elevated explicitly
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)
