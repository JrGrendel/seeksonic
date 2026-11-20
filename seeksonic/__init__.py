"""SeekSonic application package.

Modules are imported here to register Flask routes and request handlers.
"""
from .core import app
from . import meilisearch, navidrome, sync, proxy, admin_ui, runtime

__all__ = ['__all__']
