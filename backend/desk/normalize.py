"""Text normalization shared by the importer and by task matching.

Both sides must agree: an episode's stored task_name and a request's stored
task_name are compared for equality during assignment, so they have to be
normalized by the same function or the match silently fails on whitespace.
"""

from __future__ import annotations

import re

_WHITESPACE = re.compile(r"\s+")


def collapse(value: str | None) -> str:
    """Trim, and collapse any internal whitespace run to a single space."""
    if value is None:
        return ""
    return _WHITESPACE.sub(" ", value).strip()


def normalize_episode_id(value: str | None) -> str:
    """Uppercase. 'ep-00003' and 'EP-00003' are one episode, not two."""
    return collapse(value).upper()


def normalize_robot_id(value: str | None) -> str:
    return collapse(value).lower()


def normalize_task_name(value: str | None) -> str:
    """Lowercase: '  Pick Cup ', 'PICK CUP' and 'pick cup' are one task."""
    return collapse(value).lower()


def normalize_quality(value: str | None) -> str:
    return collapse(value).lower()


def normalize_operator_name(value: str | None) -> str:
    """Whitespace only. Operator names keep their original casing."""
    return collapse(value)
