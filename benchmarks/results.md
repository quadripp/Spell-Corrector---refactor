# Benchmark results

- Python 3.13.17 (CPython), Linux-6.18.44-fc-v185-x86_64-with-glibc2.39
- CPU: Intel(R) Xeon(R) Processor @ 2.10GHz, 2 logical cores
- Run on 2026-11-02 07:26 UTC

## Start-up (median of 3 runs)

| Start-up step | Time |
|---|---|
| Original: import spell.py | 0.28 s |
| Refactored: SpellCorrector.from_corpus() | 1.24 s |
| Refactored: SpellCorrector.load() from pickle | 0.47 s |

Pickle cache file size: 17.7 MB

## Memory (tracemalloc)

| Start-up step | Peak during start-up | Kept afterwards |
|---|---|---|
| Original: import spell.py | 71.7 MB | 2.6 MB |
| Refactored: SpellCorrector.from_corpus() | 123.7 MB | 122.7 MB |
| Refactored: SpellCorrector.load() from pickle | 140.5 MB | 122.7 MB |

## Time per correction

| Tier | Words | Original median | Original p95 | Refactored median | Refactored p95 | Speedup (median) |
|---|---|---|---|---|---|---|
| known word | 112 | 0.00116 ms | 0.00237 ms | 0.000379 ms | 0.000845 ms | 3.1x |
| 1 edit | 200 | 0.113 ms | 0.175 ms | 0.0994 ms | 0.159 ms | 1.1x |
| 2 edits | 200 | 49.2 ms | 103 ms | 0.399 ms | 0.679 ms | 123.2x |
| no correction found | 200 | 48.4 ms | 84.7 ms | 0.273 ms | 0.432 ms | 177.4x |
| all words | 712 | 28.2 ms | 85.5 ms | 0.222 ms | 0.537 ms | 127.0x |

Total for all 712 words: original 21.29 s, refactored 0.165 s, 129x faster.

Answers: 709 identical, 3 equal-count ties, 0 other differences.
