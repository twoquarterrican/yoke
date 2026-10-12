"""Default loopback address of the local-universe UI server (``yoke ui``).

Collision-probed at startup; ``--host`` and ``--port`` on ``yoke ui``
override within the same loopback-only security boundary. Clients that
compose local links (such as shared-file URLs) read the defaults here.
"""

DEFAULT_UI_HOST = "127.0.0.1"
DEFAULT_UI_PORT = 8688

__all__ = ["DEFAULT_UI_HOST", "DEFAULT_UI_PORT"]
