"""A faster version of Peter Norvig's spelling corrector.

The original is in original/spell.py (MIT license, Copyright (c) 2007-2016
Peter Norvig, http://norvig.com/spell-correct.html). This version gives the
same answers. The only part that changed is how words two edits away are
found: the original generates every string two edits away from the input,
and this version looks them up in a precomputed index instead.
"""

from __future__ import annotations

import os
import pickle
import re
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping

# Norvig's model can only insert or substitute these 26 letters, even though
# dictionary words may also contain digits and underscores.
LETTERS = 'abcdefghijklmnopqrstuvwxyz'


def words(text: str) -> list[str]:
    """Split text into lowercase words, exactly as the original does."""
    return re.findall(r'\w+', text.lower())


def edits1(word: str) -> set[str]:
    """All strings one edit away from `word` (same code as the original)."""
    splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
    deletes = [L + R[1:] for L, R in splits if R]
    transposes = [L + R[1] + R[0] + R[2:] for L, R in splits if len(R) > 1]
    replaces = [L + c + R[1:] for L, R in splits if R for c in LETTERS]
    inserts = [L + c + R for L, R in splits for c in LETTERS]
    return set(deletes + transposes + replaces + inserts)


def deletions(word: str) -> set[str]:
    """`word` itself plus every string made by deleting one or two characters."""
    one = {word[:i] + word[i + 1:] for i in range(len(word))}
    two = {d[:i] + d[i + 1:] for d in one for i in range(len(d))}
    return {word} | one | two


def reverse_edits1(word: str, alphabet: set[str]) -> set[str]:
    """Every string m such that `word` is in edits1(m).

    Each of Norvig's four edits is undone by one reverse edit. A character
    that m had but `word` lost could have been anything, so we try every
    character in `alphabet`. The caller passes a-z plus the characters of
    the misspelled input, because those are the only characters the middle
    string of a two-edit path can contain.
    """
    splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
    # m -> word by deleting a character: put any character back.
    undo_deletes = [L + c + R for L, R in splits for c in alphabet]
    # m -> word by inserting an a-z letter: remove an a-z letter.
    undo_inserts = [L + R[1:] for L, R in splits if R and R[0] in LETTERS]
    # m -> word by replacing a character with an a-z letter: put any character back.
    undo_replaces = [L + c + R[1:] for L, R in splits
                     if R and R[0] in LETTERS for c in alphabet]
    # m -> word by swapping two neighbours: swap them back.
    undo_transposes = [L + R[1] + R[0] + R[2:] for L, R in splits if len(R) > 1]
    return set(undo_deletes + undo_inserts + undo_replaces + undo_transposes)


def build_delete_index(vocabulary: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """Map every string made by deleting 0, 1 or 2 characters from a word to that word.

    Example: 'cat' is stored under 'cat', 'at', 'ct', 'ca', 'a', 'c' and 't'.
    """
    index: dict[str, tuple[str, ...]] = {}
    for word in vocabulary:
        for d in deletions(word):
            # Values are tuples because they use less memory than lists
            # (see benchmarks/memory_experiment.py). Adding a word builds a
            # new tuple, which copies the old one, but most keys hold a single
            # word and the largest holds a few hundred, so the copying is cheap.
            index[d] = index.get(d, ()) + (word,)
    return index


class SpellCorrector:
    """Norvig's spelling corrector with a delete index for two-edit lookups."""

    def __init__(self, word_counts: Mapping[str, int]) -> None:
        """Build the corrector from a mapping of word -> number of occurrences."""
        # Copy the counts so a caller who changes their Counter later cannot
        # make our index disagree with our dictionary.
        self.counts: Counter[str] = Counter(word_counts)
        self.total = sum(self.counts.values())
        self.index = build_delete_index(self.counts)

    @classmethod
    def from_corpus(cls, path: str | os.PathLike[str]) -> SpellCorrector:
        """Count the words in a text file (like the original's big.txt) and build."""
        # The text and the token list are only needed inside this block, so
        # they are freed before the index is built. That keeps peak memory lower.
        with open(path, encoding='utf-8') as f:
            counts = Counter(words(f.read()))
        return cls(counts)

    def save(self, path: str | os.PathLike[str]) -> None:
        """Pickle the whole corrector so a later start-up can skip building the index."""
        with open(path, 'wb') as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> SpellCorrector:
        """Load a corrector written by save().

        Only load files you created yourself: unpickling a file from someone
        else can run arbitrary code. If the corpus changes, delete the file.
        """
        with open(path, 'rb') as f:
            corrector = pickle.load(f)
        if not isinstance(corrector, cls):
            raise TypeError(f'{path} does not contain a {cls.__name__}')
        return corrector

    def P(self, word: str) -> float:
        """Probability of `word`."""
        return self.counts[word] / self.total

    def known(self, candidates: Iterable[str]) -> set[str]:
        """The subset of `candidates` that appear in the dictionary."""
        return {w for w in candidates if w in self.counts}

    def correction(self, word: str) -> str:
        """Most probable spelling correction for `word`."""
        if word in self.counts:
            return word
        one_edit = edits1(word)
        known_one_edit = self.known(one_edit)
        if known_one_edit:
            return min(known_one_edit, key=self._rank)
        # _two_edit_words yields words from most to least frequent, so the
        # first one is the answer and we can skip checking the rest.
        return next(self._two_edit_words(word, one_edit), word)

    def candidates(self, word: str) -> set[str]:
        """Possible corrections: the same set the original returns."""
        if word in self.counts:
            return {word}
        one_edit = edits1(word)
        known_one_edit = self.known(one_edit)
        if known_one_edit:
            return known_one_edit
        return set(self._two_edit_words(word, one_edit)) or {word}

    def _rank(self, word: str) -> tuple[int, str]:
        """Sort key: highest count first, then alphabetical.

        The original uses max() over a set, so when two candidates have the
        same count its answer depends on set order, which changes between
        runs. The alphabetical tie-break gives one fixed answer.
        """
        return (-self.counts[word], word)

    def _two_edit_words(self, word: str, one_edit: set[str]) -> Iterator[str]:
        """Yield dictionary words exactly two of Norvig's edits from `word`, best first.

        `one_edit` must be edits1(word); the caller already has it from tier 1.
        """
        # Step 1: a cheap superset. If two edits turn `word` into w, then
        # deleting at most two characters from each gives the same string,
        # so w is stored under one of the deletions of `word`.
        possible: set[str] = set()
        for d in deletions(word):
            possible.update(self.index.get(d, ()))

        # Step 2: the exact test. Norvig's edits2 means "edits1 applied
        # twice", so w passes if some middle string m is one edit from
        # `word` (m is in one_edit) and w is one edit from m (m is in
        # reverse_edits1(w)). That is the original's definition, so the
        # test cannot disagree with it.
        alphabet = set(LETTERS) | set(word)
        for w in sorted(possible, key=self._rank):
            if not one_edit.isdisjoint(reverse_edits1(w, alphabet)):
                yield w
