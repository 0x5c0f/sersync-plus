"""
Sersync Python - Real-time file synchronization tool

A Python implementation of sersync with extended features:
- Real-time file monitoring and synchronization
- Web management dashboard
- Multi-channel notifications (Apprise)
- Bidirectional sync support (Unison)
"""

__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from sersync.core.engine import SersyncEngine
from sersync.config.models import SersyncConfig

__all__ = ["SersyncEngine", "SersyncConfig", "__version__"]
