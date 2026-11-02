"""Helpers shared by the tests and the benchmark.

They find the corpus, import Norvig's original file without editing it, and
make the same seeded list of test words every time.
"""

from __future__ import annotations

import importlib.util
import os
import random
from pathlib import Path
from types import ModuleType

from spell_corrector import LETTERS, SpellCorrector, edits1

REPO_ROOT = Path(__file__).resolve().parent
ORIGINAL_FILE = REPO_ROOT / 'original' / 'spell.py'
DEFAULT_CORPUS = REPO_ROOT / 'data' / 'big.txt'

# Tier names used in test reports and the benchmark table.
KNOWN, ONE_EDIT, TWO_EDITS, NO_CORRECTION = (
    'known word', '1 edit', '2 edits', 'no correction found')
TIERS = [KNOWN, ONE_EDIT, TWO_EDITS, NO_CORRECTION]


def find_corpus(path: str | None = None) -> Path:
    """Return the corpus path: an explicit argument, then $SPELL_CORPUS, then data/big.txt."""
    chosen = Path(path or os.environ.get('SPELL_CORPUS') or DEFAULT_CORPUS)
    if not chosen.is_file():
        raise FileNotFoundError(
            f'Corpus not found at {chosen}. Run "python scripts/download_corpus.py" '
            'or set SPELL_CORPUS to the path of big.txt.')
    return chosen


def load_original(corpus: Path) -> ModuleType:
    """Import original/spell.py as a module called norvig_spell.

    The original reads 'big.txt' from the current directory when it is
    imported, so we step into the corpus folder for the import and step back
    out afterwards. The file itself is never modified.
    """
    if corpus.name != 'big.txt':
        raise ValueError("The original opens a file named 'big.txt', so the corpus must use that name.")
    spec = importlib.util.spec_from_file_location('norvig_spell', ORIGINAL_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous_dir = os.getcwd()
    os.chdir(corpus.parent)
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(previous_dir)
    return module


EDIT_KINDS = ('delete', 'transpose', 'replace', 'insert')


def random_edit(word: str, rng: random.Random, alphabet: str = LETTERS,
                kinds: tuple[str, ...] = EDIT_KINDS) -> str:
    """Apply one random edit, chosen from `kinds`, to `word`."""
    kind = rng.choice(kinds)
    if kind == 'transpose' and len(word) < 2:
        kind = 'insert'
    if kind in ('delete', 'replace') and not word:
        kind = 'insert'
    if kind == 'delete':
        i = rng.randrange(len(word))
        return word[:i] + word[i + 1:]
    if kind == 'transpose':
        i = rng.randrange(len(word) - 1)
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    if kind == 'replace':
        i = rng.randrange(len(word))
        return word[:i] + rng.choice(alphabet) + word[i + 1:]
    i = rng.randrange(len(word) + 1)
    return word[:i] + rng.choice(alphabet) + word[i:]


def make_test_words(vocabulary: list[str], seed: int = 2026) -> list[tuple[str, str]]:
    """Return (kind, word) pairs. The same seed always gives the same list."""
    rng = random.Random(seed)
    # Sort first so the list does not depend on Counter insertion order.
    plain = sorted(w for w in vocabulary if 3 <= len(w) <= 12 and w.isalpha())
    odd = sorted(w for w in vocabulary if not w.isalpha())  # digits or underscores
    tests: list[tuple[str, str]] = []
    for _ in range(1200):
        tests.append(('typo, 1 random edit', random_edit(rng.choice(plain), rng)))
    for _ in range(1200):
        word = random_edit(random_edit(rng.choice(plain), rng), rng)
        tests.append(('typo, 2 random edits', word))
    for _ in range(300):
        length = rng.randint(3, 10)
        tests.append(('random non-word', ''.join(rng.choice(LETTERS) for _ in range(length))))
    for _ in range(100):
        # Only replace or insert, so the result always contains a digit.
        word = random_edit(rng.choice(plain), rng, alphabet='0123456789',
                           kinds=('replace', 'insert'))
        tests.append(('digits', word))
    for _ in range(50):
        # Dictionary entries such as '1812' or '_see_', with one a-z edit.
        tests.append(('digits', random_edit(rng.choice(odd), rng)))
    for _ in range(50):
        tests.append(('digits', str(rng.randrange(100, 1_000_000))))
    for word in ['', 'a', 'Speling', 'SPELLING', 'café', 'x_y', '_teh_', 'quintessential']:
        tests.append(('edge case', word))
    return tests


def tier_of(corrector: SpellCorrector, word: str) -> str:
    """Which of Norvig's tiers decides the answer for `word`."""
    if word in corrector.counts:
        return KNOWN
    if corrector.known(edits1(word)):
        return ONE_EDIT
    if corrector.candidates(word) == {word}:
        return NO_CORRECTION
    return TWO_EDITS
