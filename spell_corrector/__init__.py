"""A faster version of Peter Norvig's spelling corrector with identical answers."""

from .corrector import (
    LETTERS,
    SpellCorrector,
    build_delete_index,
    deletions,
    edits1,
    reverse_edits1,
    words,
)

__all__ = [
    'LETTERS',
    'SpellCorrector',
    'build_delete_index',
    'deletions',
    'edits1',
    'reverse_edits1',
    'words',
]
