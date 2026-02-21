"""Public package exports for the Python SDK.

Expose the same class name used in `client.py` so imports across the
package are consistent (use `ModexiaClient`).
"""
from .client import ModexiaClient

__all__ = ["ModexiaClient"]