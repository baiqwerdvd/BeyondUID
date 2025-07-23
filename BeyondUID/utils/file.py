import json
from pathlib import Path

from gsuid_core.logger import logger


def read_json(file_path: Path, **kwargs) -> dict:
    """
    Read a JSON file and return its contents as a dictionary.
    """
    try:
        with Path.open(file_path, encoding="UTF-8", **kwargs) as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Error reading JSON file: {e}")
        return {}


def write_json(data: dict, file_path: Path) -> None:
    """
    Write a dictionary to a JSON file.
    """
    try:
        with Path.open(file_path, mode="w", encoding="UTF-8") as file:
            json.dump(data, file, sort_keys=False, indent=4, ensure_ascii=False)
    except FileNotFoundError as e:
        logger.error(f"Error writing JSON file: {e}")
