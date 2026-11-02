# Spelling corrector refactor

This is a faster rewrite of Peter Norvig's spelling corrector. Norvig explains the original in his essay [How to Write a Spelling Corrector](http://norvig.com/spell-correct.html), and the code lives in his pytudes repository as [py/spell.py](https://github.com/norvig/pytudes/blob/main/py/spell.py). A copy of that file is in `original/spell.py`. It is byte for byte the same as the upstream file and I have not edited it. The original is MIT licensed, as its header says, so the LICENSE file here keeps Norvig's copyright line and adds mine for the new code.

The rewrite gives the same corrections as the original. On my benchmark it was 129 times faster over a mixed set of 712 test words, and 123 to 177 times faster (by median) on words that need two edits or have no correction. The cost is about one extra second of start-up and about 120 MB of extra memory.

## Why the original is slow

`candidates()` on line 26 of `original/spell.py` tries three tiers in order: the word itself, dictionary words one edit away, then dictionary words two edits away.

```python
return (known([word]) or known(edits1(word)) or known(edits2(word)) or [word])
```

`edits1()` on lines 32 to 40 builds every string one edit away. For a word of length n that is n deletions, n - 1 transpositions, 26n replacements and 26(n + 1) insertions, so 54n + 25 strings before duplicates are removed. This part is cheap. For the 9-letter `korrectud` it gives 492 distinct strings.

`edits2()` on lines 42 to 44 calls `edits1()` again on every one of those strings:

```python
return (e2 for e1 in edits1(word) for e2 in edits1(e1))
```

For `korrectud` that is 254,812 strings, and `known()` looks each one up in the dictionary. One of them, `corrected`, is a real word. Every word that is unknown and has no dictionary word one edit away pays this price. Words with no correction at all pay it too, because `known()` has to run through the whole generator before it can say the result is empty.

## How the new version works

The first two tiers are unchanged. If the word is in the dictionary it comes straight back. Otherwise `edits1()` runs exactly as before and its results are checked against the dictionary. Only the third tier is new, and it has two steps.

### Step 1: a delete index, built once

At start-up the corrector takes every dictionary word and makes every string you can get by deleting zero, one or two of its characters. It stores those strings in a Python dict that maps each one back to the words that produced it. So `corrected` is stored under `corrected`, under one-deletion strings like `orrected`, and under two-deletion strings like `orrectd`. The 32,198 dictionary words produce 918,414 distinct strings. This is the idea behind Wolf Garbe's [SymSpell](https://github.com/wolfgarbe/SymSpell).

To correct a word, the corrector makes the same zero, one and two deletion strings of the misspelling and looks each one up. Every dictionary word found this way is a possible answer.

A small worked example, with `korrectud`, which needs two replacements:

1. `korrectud` has 38 distinct deletion strings. One of them is `orrectd`, made by deleting the `k` and the `u`.
2. When the index was built, `corrected` was stored under `orrectd`, made by deleting the first `c` and the second-to-last `e`.
3. Looking up `orrectd` finds `corrected`. A replacement looks like a deletion at the same place on both sides, which is why the two strings meet.

For `korrectud` the 38 lookups return a single possible word. The original generated 254,812 strings to get there.

The index never misses a word that is within two edits. Any single edit between two strings can be undone by deleting at most one character from each of them. For an insertion or deletion, remove the extra character from the longer string. For a replacement, remove that position from both. For a transposition, remove one of the two swapped letters from both. Two edits pass through a middle string m. If q and m become equal after removing one character at most from each, and the same holds for m and w, then removing both of those characters from m gives a string that q and w can each reach with two deletions at most. That string is in both deletion sets, so the lookup finds w.

### Step 2: an exact check of each possible word

The index only narrows the search. It also returns words that are further away. For example `abcd` and `cdab` share the deletion string `cd`, but turning one into the other takes four of Norvig's edits. Over the 1,187 test words that reached this tier, the index returned 17,232 possible words and 4,581 of them were truly within two edits. So each possible word has to be checked.

Norvig's rule is: w is within two edits of q if there is a middle string m with m in `edits1(q)` and w in `edits1(m)`. The code already has `edits1(q)` from tier 1. For a possible word w, `reverse_edits1(w)` builds every string m for which w would appear in `edits1(m)`. It does that by undoing each kind of edit:

- Undo an insertion by removing a character from w. Only a-z characters count, because Norvig only ever inserts a-z.
- Undo a replacement by putting a different character back. Again this only applies where w has an a-z character.
- Undo a deletion by putting a character back.
- Undo a transposition by swapping the two letters back.

If `edits1(q)` and `reverse_edits1(w)` share any string, that string is the middle step and w passes. This is Norvig's own definition, worked from both ends at once. It accepts exactly the words his `edits2()` finds, and there is no separate distance formula that could drift from his rules.

One detail needs care. When undoing a deletion, which characters should be tried? The middle string came out of `edits1(q)`, so every character in it is either a character of q or a letter a-z. Trying a-z plus the characters of q therefore covers every middle string that could exist. For `corrected`, `reverse_edits1` makes 492 strings, and two of them are also in `edits1('korrectud')`: `correctud` and `korrected`. Either one works as the middle step.

The check costs about as much as one call to `edits1()`: on my machine `reverse_edits1('corrected')` took 55 microseconds against 46 for `edits1('korrectud')`. The possible words are checked from most to least frequent and `correction()` stops at the first one that passes. On the 939 two-edit test words it ran the check once at the median and 2.5 times on average. `candidates()` checks all of them, because it has to return the full set.

## Making sure the answers match

### The tests

`tests/test_equivalence.py` loads the untouched original next to the new class and compares them.

- Norvig's own `unit_tests()` assertions, rewritten to call the new class.
- 2,908 seeded test words. 1,200 are dictionary words of length 3 to 12 with one random edit, 1,200 have two random edits, and the edits are deletions, transpositions, replacements and insertions. There are also 300 random strings of letters and 200 strings containing digits or the `_` character: dictionary words with a digit put in, dictionary entries such as `1812` or `_see_` with one random edit, and random numbers. A few edge cases such as the empty string, capital letters and `café` finish the list.
- For every word, the new `candidates()` must return the same set as the original `candidates()`. This is stricter than comparing corrections. It checks every word in the two-edit set, where comparing corrections would check just the winner.
- The correction must be the same, or an equal-count tie as described below. A slice of the words also goes through the original `correction()` directly.

Of the 2,908 words, 112 are dictionary words, 1,609 are decided by one edit, 939 by two edits, and 248 have no correction. Every candidate set matched.

### Ties

The original `correction()` on line 22 is `max(candidates(word), key=P)`. `candidates()` returns a set, and when two words have the same count `max()` keeps whichever it meets first. The order of a set of strings depends on Python's hash randomisation, which changes on every run unless PYTHONHASHSEED is fixed. So the original can give different answers for the same word on different runs. For `sdneyf`, both `sidney` and `sydney` appear twice in the corpus, and the original returned `sidney` with PYTHONHASHSEED set to 0, 1, 2, 3 and 7 but `sydney` with 4, 5 and 6.

The new version breaks ties by highest count first and then alphabetical order, so it always returns `sidney`. The tests accept a different answer from the original only when both answers come from the same candidate set, which means the same tier, and have the same count. I ran the full suite with a random hash seed and with PYTHONHASHSEED set to 0, 1, 777 and 4242. All runs passed. The number of words where the original happened to pick the other tied word ranged from 29 to 36 out of 2,908.

### The edit distance subtlety

My first sketch checked the possible words with optimal string alignment distance, a restricted form of Damerau-Levenshtein distance. It disagreed with the original on `lgaso` and `peaceflou`. Norvig's model lets you delete a letter and then swap the two letters that become neighbours: `lgaso` to `laso` to `also`, and `peaceflou` to `peaceflu` to `peaceful`. Optimal string alignment never edits the same stretch of text twice, so it counts both of those as three edits and rejected `also` and `peaceful`. In distance terms, Norvig's model is the unrestricted Damerau-Levenshtein distance, with one twist: insertions and replacements can only use a-z, even though dictionary words can contain digits and the `_` character. The check above avoids the whole question because it is built from Norvig's own edits. A test covers both words.

### Differences from the original

- Ties between equal counts are broken by alphabetical order instead of set order.
- When nothing is found, `candidates()` returns the set `{word}` where the original returns the list `[word]`. It always returns a set.
- Nothing happens at import. You build a corrector from a word Counter or call `SpellCorrector.from_corpus(path)`, where the original opens `big.txt` in the current folder when the module is imported.
- `from_corpus()` reads the file as UTF-8. The original uses the platform's default encoding. `big.txt` is plain ASCII, so this makes no difference for it.
- `P()` is a method on the object and returns the same values.

## Results

These numbers come from `python benchmarks/benchmark.py` on a cloud Linux VM with 2 cores (Intel Xeon @ 2.10GHz) and Python 3.13.17. The full output is in `benchmarks/results.md`. Timings will be different on other machines. I ran the benchmark four times while working on this, the first two with a slightly earlier version of the word list, and the total speedup came out between 119x and 129x.

| Tier | Words | Original median | Original p95 | Refactored median | Refactored p95 | Speedup (median) |
|---|---|---|---|---|---|---|
| known word | 112 | 0.00116 ms | 0.00237 ms | 0.000379 ms | 0.000845 ms | 3.1x |
| 1 edit | 200 | 0.113 ms | 0.175 ms | 0.0994 ms | 0.159 ms | 1.1x |
| 2 edits | 200 | 49.2 ms | 103 ms | 0.399 ms | 0.679 ms | 123.2x |
| no correction found | 200 | 48.4 ms | 84.7 ms | 0.273 ms | 0.432 ms | 177.4x |
| all words | 712 | 28.2 ms | 85.5 ms | 0.222 ms | 0.537 ms | 127.0x |

Total for all 712 words: original 21.29 s, refactored 0.165 s, 129x faster. The benchmark also compared every answer: 709 identical and 3 equal-count ties.

The words are the first 200 from each tier of the same seeded list the tests use. Only 112 words on that list are dictionary words, so the first row is shorter. The known-word tier is faster because the new code checks `word in counts` directly, where the original builds a one-element set and calls `max()` on it. The gain there is under a microsecond. The one-edit tier runs the same code as the original, so it takes about the same time.

## Trade-offs

### Start-up

| Start-up step | Time (median of 3) |
|---|---|
| Original: import spell.py | 0.28 s |
| Refactored: SpellCorrector.from_corpus() | 1.24 s |
| Refactored: SpellCorrector.load() from pickle | 0.47 s |

Building the index adds about a second. To cut that, `save()` writes the whole corrector to a pickle file (17.7 MB) and `load()` reads it back. Loading was 2.6 times faster than building, though still slower than the original's start-up. Two warnings come with it. Pickle files can run code when loaded, so only load files you made yourself. The cache is not checked against the corpus either, so delete it if `big.txt` changes.

### Memory

Measured with `tracemalloc`:

| Start-up step | Peak during start-up | Kept afterwards |
|---|---|---|
| Original: import spell.py | 71.7 MB | 2.6 MB |
| Refactored: SpellCorrector.from_corpus() | 123.7 MB | 122.7 MB |
| Refactored: SpellCorrector.load() from pickle | 140.5 MB | 122.7 MB |

The original keeps 2.6 MB once it has started, which is just the word counts. The new version keeps 122.7 MB for as long as the corrector exists, about 47 times more, and almost all of it is the delete index. The original's 71.7 MB peak comes from the corpus text and the list of 1.1 million tokens, which together came to 65.2 MB when I measured them on their own. `from_corpus()` lets those go before it builds the index, so the two peaks do not stack.

I tried a few ways of storing the index (`python benchmarks/memory_experiment.py`; these numbers cover the index alone):

| Index storage | Build time | Peak during build | Kept after build |
|---|---|---|---|
| lists, appended to | 1.08 s | 139.2 MB | 139.2 MB |
| lists, converted to tuples at the end | 1.46 s | 139.2 MB | 120.2 MB |
| tuples, extended by concatenation (used) | 0.95 s | 120.2 MB | 120.2 MB |
| tuples plus sys.intern() on keys | 1.23 s | 150.9 MB | 150.9 MB |

Tuples saved 19 MB over lists, about 14%. A one-element list needs two blocks of memory, the list object and a separate array for its items. A tuple keeps its items inside the object, and with 918,414 entries the difference adds up. Building each tuple with `index.get(d, ()) + (word,)` copies the old tuple every time a word is added, which sounds wasteful. In practice 89% of the deletion strings belong to a single word and the longest tuple has 329 words, so the copying stays small, and this was the fastest build of the four. It never creates the lists at all, so its peak stays at 120.2 MB. Converting lists at the end saves the same memory in the long run, but its peak is still the full size of the list version.

Interning the strings made things worse by about 31 MB, so I dropped it. Every string in the index is already stored once. The dictionary words inside the tuples are the same string objects the Counter holds, so they are not copied either. Interning had nothing to share and only added the interpreter's own intern table.

## Repository layout

- `original/spell.py` is Norvig's file, unchanged.
- `spell_corrector/corrector.py` holds the `SpellCorrector` class and the helper functions `edits1()`, `deletions()`, `reverse_edits1()` and `build_delete_index()`.
- `harness.py` is shared by the tests and the benchmarks. It finds the corpus, imports the original file with `importlib` after changing into the corpus folder (the original opens `big.txt` from the current folder when it is imported), builds the seeded list of test words, and works out which tier decides each word.
- `tests/test_equivalence.py` holds the equivalence tests.
- `benchmarks/benchmark.py` measures speed and memory and writes `benchmarks/results.md`. `benchmarks/memory_experiment.py` compares the index storage options.
- `scripts/download_corpus.py` downloads `big.txt`.
- `pytest.ini` puts the repository root on the import path for the tests.

## How to run

You need Python 3.10 or newer.

```bash
pip install -r requirements.txt
python scripts/download_corpus.py      # saves data/big.txt (6.5 MB, not committed)
python -m pytest -s                    # about 70 to 100 seconds
python benchmarks/benchmark.py         # about 40 seconds, writes benchmarks/results.md
python benchmarks/memory_experiment.py # about 30 seconds
```

Most of the test time is the original working through `edits2()` for 2,908 words.

If `big.txt` is somewhere else, set `SPELL_CORPUS=/path/to/big.txt` or pass `--corpus /path/to/big.txt` to the benchmark scripts. The file has to be named `big.txt`, because that is the name the original opens.

Using the class:

```python
from collections import Counter
from spell_corrector import SpellCorrector

corrector = SpellCorrector.from_corpus('data/big.txt')
corrector.correction('speling')      # 'spelling'
corrector.candidates('korrectud')    # {'corrected'}

small = SpellCorrector(Counter({'hello': 3, 'help': 1}))
small.correction('helo')             # 'hello'
```
