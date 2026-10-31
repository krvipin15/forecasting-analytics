"""Application Settings and Configuration Management.

This module defines the type-safe application configuration schema using
Pydantic Settings and Pydantic v2. It manages environment variables, `.env` file
overrides, runtime directories, and hyperparameter configuration (`params.yaml`).
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_project_root(current_path: Path) -> Path:
    """Locate the project root by searching for known anchor files.

    Starting from ``current_path``, recursively walks up the directory tree
    until a directory containing the project's anchor files is found.

    Parameters
    ----------
    current_path : pathlib.Path
        Starting path from which the parent directories are searched.

    Returns
    -------
    pathlib.Path
        Path to the detected project root directory.
    """
    for parent in [current_path, *list(current_path.parents)]:
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            return parent

    return current_path.resolve().parents[2]


# Get the base directory for the project
BASE_DIR = _find_project_root(Path(__file__).resolve())


class Environment(StrEnum):
    """Enumeration of supported application logging levels."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class LogLevel(StrEnum):
    """Enumeration of logging levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    """Define validated application-wide runtime configuration.

    Configuration values are loaded from environment variables and the
    project-level ``.env`` file, with environment variables taking
    precedence.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Runtime configuration
    ENVIRONMENT: Environment = Field(default=Environment.DEVELOPMENT)
    LOG_LEVEL: LogLevel = Field(default=LogLevel.INFO)
    LOGGER_NAME: str = Field(default="forecast_analytics", min_length=1)

    # Workspace Paths
    LOGS_DIR: Path = Field(default_factory=lambda: BASE_DIR / "logs")

    def ensure_directories(self) -> None:
        """Create required application workspace directories.

        Ensures that directories required for data ingestion, preprocessing,
        models, reports, predictions, logs, and other runtime artifacts exist.
        Existing directories are left unchanged.
        """
        directories = [
            self.LOGS_DIR,
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings.

    Local development may use a project-level environment file, while
    deployment environments such as Render provide configuration directly
    through environment variables.
    """
    settings = Settings()
    settings.ensure_directories()

    return settings
