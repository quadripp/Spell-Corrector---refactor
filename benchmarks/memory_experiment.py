"""Compare ways of storing the delete index, by memory and build time.

The word counts are built first and are not included in these numbers, so
each row shows the cost of the index alone. Usage:
    python benchmarks/memory_experiment.py [--corpus PATH]
"""

from __future__ import annotations

import argparse
import gc
import sys
import time
import tracemalloc
from collections.abc import Callable, Iterable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import find_corpus  # noqa: E402
from spell_corrector import SpellCorrector, build_delete_index, deletions  # noqa: E402

Index = dict[str, object]


def lists(vocabulary: Iterable[str]) -> Index:
    """The obvious version: a list of words per key, appended to as we go."""
    index: dict[str, list[str]] = {}
    for word in vocabulary:
        for d in deletions(word):
            if d in index:
                index[d].append(word)
            else:
                # [word] makes a list with exactly one slot. Starting from []
                # and appending would reserve spare slots and use more memory,
                # which would make this baseline look worse than it needs to.
                index[d] = [word]
    return index


def lists_then_tuples(vocabulary: Iterable[str]) -> Index:
    """Build lists, then swap each one for a tuple once the index is complete."""
    index: Index = lists(vocabulary)
    for key, value in index.items():
        index[key] = tuple(value)
    return index


def interned_keys(vocabulary: Iterable[str]) -> Index:
    """Tuples (as in the package) plus sys.intern() on every key."""
    index: dict[str, tuple[str, ...]] = {}
    for word in vocabulary:
        for d in deletions(word):
            d = sys.intern(d)
            index[d] = index.get(d, ()) + (word,)
    return index


VARIANTS: list[tuple[str, Callable[[Iterable[str]], Index]]] = [
    ('lists, appended to', lists),
    ('lists, converted to tuples at the end', lists_then_tuples),
    ('tuples, extended by concatenation (used)', build_delete_index),
    ('tuples plus sys.intern() on keys', interned_keys),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--corpus', help='path to big.txt (default: $SPELL_CORPUS or data/big.txt)')
    args = parser.parse_args()
    vocabulary = list(SpellCorrector.from_corpus(find_corpus(args.corpus)).counts)

    print('| Index storage | Build time | Peak during build | Kept after build |')
    print('|---|---|---|---|')
    for name, build in VARIANTS:
        gc.collect()
        start = time.perf_counter()
        index = build(vocabulary)
        seconds = time.perf_counter() - start
        del index
        gc.collect()

        # A second build under tracemalloc, because tracing slows Python down
        # and would distort the build time above.
        tracemalloc.start()
        index = build(vocabulary)
        kept, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        del index
        print(f'| {name} | {seconds:.2f} s | {peak / 1e6:.1f} MB | {kept / 1e6:.1f} MB |')


if __name__ == '__main__':
    main()
