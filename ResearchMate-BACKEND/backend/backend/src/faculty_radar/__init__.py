"""Faculty Research Discovery Assistant.

A research intelligence engine that ranks faculty by topic expertise, backed
by an auditable evidence trail rather than model recall.
"""

from faculty_radar.config import Settings, configure_logging, get_logger, get_settings
from faculty_radar.paths import DataPaths, paths

__version__ = "0.1.0"

__all__ = [
    "DataPaths",
    "Settings",
    "__version__",
    "configure_logging",
    "get_logger",
    "get_settings",
    "paths",
]
