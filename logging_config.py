import logging
from typing import Optional
from logging import StreamHandler, FileHandler

def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    handlers: list[logging.Handler] = [StreamHandler()]
    if log_file:
        handlers.append(FileHandler(log_file, mode="a", encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers
    )