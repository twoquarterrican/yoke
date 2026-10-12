"""Refuse private material in the public teaching tree.

The repository is public. Home-directory paths, iCloud locations, machine
temp captures and UUID-shaped identifiers (session, user or machine ids)
must never be committed here. Patterns are assembled from parts so this
file does not match itself.
"""

from __future__ import annotations

import re

_HEX = "[0-9a-fA-F]"
PATTERNS = (
    ("home-directory path", re.compile(r"/(?:" + "Users|home" + r")/[A-Za-z0-9._-]+/")),
    ("Windows profile path", re.compile(r"[A-Za-z]:\\\\?" + "Users" + r"\\")),
    ("iCloud location", re.compile("Mobile " + "Documents|com~apple~" + "CloudDocs")),
    ("machine temp path", re.compile(r"(?<![\w.])/(?:" + "tmp|private/var|var/folders" + r")/")),
    ("UUID-shaped identifier", re.compile(
        rf"\b{_HEX}{{8}}-{_HEX}{{4}}-{_HEX}{{4}}-{_HEX}{{4}}-{_HEX}{{12}}\b")),
)
RECOVERY = (
    "remove it or replace it with a repository-relative path or a named "
    "private-evidence boundary, then rebuild"
)

