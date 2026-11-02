"""Time and memory comparison of original/spell.py and SpellCorrector.

Usage:
    python benchmarks/benchmark.py [--corpus PATH] [--per-tier N]

Prints the results and writes them to benchmarks/results.md.
"""

from __future__ import annotations

import argparse
import gc
import math
import os
import platform
import statistics
import sys
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import TIERS, find_corpus, load_original, make_test_words, tier_of  # noqa: E402
from spell_corrector import SpellCorrector  # noqa: E402

RESULTS_FILE = Path(__file__).resolve().parent / 'results.md'
STARTUP_REPEATS = 3


def cpu_name() -> str:
    """CPU model from /proc/cpuinfo on Linux, since platform.processor() is often empty there."""
    try:
        for line in Path('/proc/cpuinfo').read_text().splitlines():
            if line.startswith('model name'):
                return line.split(':', 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or 'unknown'


def percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank percentile: the smallest value with `fraction` of the values at or below it."""
    ordered = sorted(values)
    rank = max(math.ceil(fraction * len(ordered)), 1)
    return ordered[rank - 1]


def median_seconds(func: Callable[[], Any]) -> float:
    """Run `func` a few times and return the median wall-clock time."""
    times = []
    for _ in range(STARTUP_REPEATS):
        gc.collect()
        start = time.perf_counter()
        func()
        times.append(time.perf_counter() - start)
    return statistics.median(times)


def traced_memory(func: Callable[[], Any]) -> tuple[float, float]:
    """Return (peak MB while func runs, MB still held by its result afterwards)."""
    gc.collect()
    tracemalloc.start()
    result = func()  # keep the result alive so its memory counts as "kept"
    kept, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del result
    return peak / 1e6, kept / 1e6


def ms(seconds: float) -> str:
    """Milliseconds to three significant figures, so 0.0004 ms and 48.9 ms both stay readable."""
    return f'{seconds * 1000:.3g} ms'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--corpus', help='path to big.txt (default: $SPELL_CORPUS or data/big.txt)')
    parser.add_argument('--per-tier', type=int, default=200, help='test words per tier')
    args = parser.parse_args()
    corpus = find_corpus(args.corpus)
    lines: list[str] = []

    def out(text: str = '') -> None:
        print(text, flush=True)
        lines.append(text)

    out('# Benchmark results')
    out()
    out(f'- Python {platform.python_version()} ({platform.python_implementation()}), {platform.platform()}')
    out(f'- CPU: {cpu_name()}, {os.cpu_count()} logical cores')
    out(f'- Run on {time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}')
    out()

    # Start-up -----------------------------------------------------------
    original = load_original(corpus)
    corrector = SpellCorrector.from_corpus(corpus)
    with tempfile.TemporaryDirectory() as folder:
        cache = Path(folder) / 'corrector.pickle'
        corrector.save(cache)
        cache_mb = cache.stat().st_size / 1e6
        startup = [
            ('Original: import spell.py', median_seconds(lambda: load_original(corpus))),
            ('Refactored: SpellCorrector.from_corpus()', median_seconds(lambda: SpellCorrector.from_corpus(corpus))),
            ('Refactored: SpellCorrector.load() from pickle', median_seconds(lambda: SpellCorrector.load(cache))),
        ]
        memory = [
            ('Original: import spell.py', *traced_memory(lambda: load_original(corpus))),
            ('Refactored: SpellCorrector.from_corpus()', *traced_memory(lambda: SpellCorrector.from_corpus(corpus))),
            ('Refactored: SpellCorrector.load() from pickle', *traced_memory(lambda: SpellCorrector.load(cache))),
        ]

    out(f'## Start-up (median of {STARTUP_REPEATS} runs)')
    out()
    out('| Start-up step | Time |')
    out('|---|---|')
    for name, seconds in startup:
        out(f'| {name} | {seconds:.2f} s |')
    out()
    out(f'Pickle cache file size: {cache_mb:.1f} MB')
    out()
    out('## Memory (tracemalloc)')
    out()
    out('| Start-up step | Peak during start-up | Kept afterwards |')
    out('|---|---|---|')
    for name, peak, kept in memory:
        out(f'| {name} | {peak:.1f} MB | {kept:.1f} MB |')
    out()

    # Per-word latency -----------------------------------------------------
    # Take the first N test words from each tier, so every tier is measured
    # on the same number of words and the run stays short.
    chosen: dict[str, list[str]] = {tier: [] for tier in TIERS}
    for _, word in make_test_words(list(corrector.counts)):
        tier = tier_of(corrector, word)
        if len(chosen[tier]) < args.per_tier:
            chosen[tier].append(word)

    old_times: dict[str, list[float]] = {tier: [] for tier in TIERS}
    new_times: dict[str, list[float]] = {tier: [] for tier in TIERS}
    identical = ties = 0
    for tier in TIERS:
        for word in chosen[tier]:
            # Time the two versions one after the other on the same word, so
            # any slow patch on the machine affects both about equally.
            start = time.perf_counter()
            old_answer = original.correction(word)
            old_times[tier].append(time.perf_counter() - start)
            start = time.perf_counter()
            new_answer = corrector.correction(word)
            new_times[tier].append(time.perf_counter() - start)
            if new_answer == old_answer:
                identical += 1
            elif original.WORDS[new_answer] == original.WORDS[old_answer]:
                ties += 1

    all_old = [t for tier in TIERS for t in old_times[tier]]
    all_new = [t for tier in TIERS for t in new_times[tier]]
    out('## Time per correction')
    out()
    out('| Tier | Words | Original median | Original p95 | Refactored median | Refactored p95 | Speedup (median) |')
    out('|---|---|---|---|---|---|---|')
    rows = [(tier, old_times[tier], new_times[tier]) for tier in TIERS]
    rows.append(('all words', all_old, all_new))
    for name, old, new in rows:
        old_median, new_median = statistics.median(old), statistics.median(new)
        out(f'| {name} | {len(old)} | {ms(old_median)} | {ms(percentile(old, 0.95))} '
            f'| {ms(new_median)} | {ms(percentile(new, 0.95))} | {old_median / new_median:.1f}x |')
    out()
    out(f'Total for all {len(all_old)} words: original {sum(all_old):.2f} s, '
        f'refactored {sum(all_new):.3f} s, {sum(all_old) / sum(all_new):.0f}x faster.')
    out()
    out(f'Answers: {identical} identical, {ties} equal-count ties, '
        f'{len(all_old) - identical - ties} other differences.')

    RESULTS_FILE.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'\nWrote {RESULTS_FILE}')


if __name__ == '__main__':
    main()
