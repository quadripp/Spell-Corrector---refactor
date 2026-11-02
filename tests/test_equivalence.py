"""Check that SpellCorrector gives the same answers as Norvig's original code.

The corpus is found by harness.find_corpus(): $SPELL_CORPUS if set, otherwise
data/big.txt (run scripts/download_corpus.py to get it).
"""

from __future__ import annotations

from collections import Counter
from types import ModuleType

import pytest

from harness import find_corpus, load_original, make_test_words, tier_of
from spell_corrector import SpellCorrector, words


@pytest.fixture(scope='module')
def original() -> ModuleType:
    return load_original(find_corpus())


@pytest.fixture(scope='module')
def corrector() -> SpellCorrector:
    return SpellCorrector.from_corpus(find_corpus())


@pytest.fixture(scope='module')
def test_words(corrector: SpellCorrector) -> list[tuple[str, str]]:
    return make_test_words(list(corrector.counts))


def test_norvig_unit_tests(corrector: SpellCorrector) -> None:
    """The assertions from unit_tests() in original/spell.py, run against the new class."""
    c = corrector
    assert c.correction('speling') == 'spelling'               # insert
    assert c.correction('korrectud') == 'corrected'            # replace 2
    assert c.correction('bycycle') == 'bicycle'                # replace
    assert c.correction('inconvient') == 'inconvenient'        # insert 2
    assert c.correction('arrainged') == 'arranged'             # delete
    assert c.correction('peotry') == 'poetry'                  # transpose
    assert c.correction('peotryy') == 'poetry'                 # transpose + delete
    assert c.correction('word') == 'word'                      # known
    assert c.correction('quintessential') == 'quintessential'  # unknown
    assert words('This is a TEST.') == ['this', 'is', 'a', 'test']
    assert Counter(words('This is a test. 123; A TEST this is.')) == (
        Counter({'123': 1, 'a': 2, 'is': 2, 'test': 2, 'this': 2}))
    assert len(c.counts) == 32198
    assert sum(c.counts.values()) == 1115585
    assert c.counts.most_common(10) == [
        ('the', 79809),
        ('of', 40024),
        ('and', 38312),
        ('to', 28765),
        ('in', 22023),
        ('a', 21124),
        ('that', 12512),
        ('he', 12401),
        ('was', 11410),
        ('it', 10681)]
    assert c.counts['the'] == 79809
    assert c.P('quintessential') == 0
    assert 0.07 < c.P('the') < 0.08


def test_original_unit_tests_still_pass(original: ModuleType) -> None:
    """Sanity check that the untouched original loads and passes its own tests."""
    assert original.unit_tests() == 'unit_tests pass'


def test_same_dictionary(original: ModuleType, corrector: SpellCorrector) -> None:
    assert corrector.counts == original.WORDS
    for word in ['the', 'poetry', '1812', '_see_', 'zzzz']:
        assert corrector.P(word) == original.P(word)


def test_test_word_list_is_large_enough(test_words: list[tuple[str, str]]) -> None:
    kinds = Counter(kind for kind, _ in test_words)
    assert kinds['typo, 1 random edit'] + kinds['typo, 2 random edits'] >= 2000
    assert kinds['random non-word'] >= 300
    assert kinds['digits'] >= 100


def test_matches_original_on_random_words(
        original: ModuleType, corrector: SpellCorrector,
        test_words: list[tuple[str, str]]) -> None:
    """Same candidate set for every word, and the same correction apart from equal-count ties.

    original.candidates() is the slow part, so it is called once per word.
    Its correction is then worked out with the same expression the original
    uses on line 22: max(candidates(word), key=P).
    """
    same, ties, problems = 0, 0, []
    tiers: Counter[str] = Counter()
    for kind, word in test_words:
        original_candidates = set(original.candidates(word))
        new_candidates = corrector.candidates(word)
        if new_candidates != original_candidates:
            problems.append(f'{kind} {word!r}: candidate sets differ by '
                            f'{sorted(new_candidates ^ original_candidates)}')
            continue
        tiers[tier_of(corrector, word)] += 1
        original_answer = max(original_candidates, key=original.P)
        new_answer = corrector.correction(word)
        if new_answer == original_answer:
            same += 1
        elif (new_answer in original_candidates
              and original.WORDS[new_answer] == original.WORDS[original_answer]):
            # Both answers come from the same candidate set (so the same tier)
            # and have equal counts: the original chose by set order.
            ties += 1
        else:
            problems.append(f'{kind} {word!r}: original {original_answer!r}, new {new_answer!r}')
    print(f'\n{len(test_words)} words: {same} identical, {ties} equal-count ties, '
          f'{len(problems)} problems; tiers {dict(tiers)}')
    assert not problems, '\n'.join(problems[:20])
    # Make sure the random words really exercise the two-edit and no-match paths.
    assert tiers['2 edits'] >= 500 and tiers['no correction found'] >= 50


def test_correction_called_directly(original: ModuleType, corrector: SpellCorrector,
                                    test_words: list[tuple[str, str]]) -> None:
    """Call original.correction() itself on a slice of the words, for extra certainty."""
    for _, word in test_words[::15]:
        original_answer = original.correction(word)
        new_answer = corrector.correction(word)
        if new_answer != original_answer:
            assert original.WORDS[new_answer] == original.WORDS[original_answer]
            assert new_answer in original.candidates(word)


def test_ties_are_broken_by_count_then_alphabet(
        corrector: SpellCorrector, test_words: list[tuple[str, str]]) -> None:
    found_a_tie = False
    for _, word in test_words:
        candidates = corrector.candidates(word)
        best = max(corrector.counts[w] for w in candidates)
        top = sorted(w for w in candidates if corrector.counts[w] == best)
        assert corrector.correction(word) == top[0]
        found_a_tie = found_a_tie or len(top) > 1
    assert found_a_tie, 'the word list should contain at least one tie'


def test_pickle_cache_round_trip(corrector: SpellCorrector, tmp_path) -> None:
    path = tmp_path / 'corrector.pickle'
    corrector.save(path)
    loaded = SpellCorrector.load(path)
    assert loaded.counts == corrector.counts
    assert loaded.total == corrector.total
    assert loaded.index == corrector.index
    for word in ['speling', 'lgaso', 'peaceflou', 'quintessential']:
        assert loaded.correction(word) == corrector.correction(word)


def test_examples_from_the_first_sketch(original: ModuleType, corrector: SpellCorrector) -> None:
    """Two words where an optimal-string-alignment check disagreed with the original."""
    for word in ['lgaso', 'peaceflou']:
        assert corrector.candidates(word) == set(original.candidates(word))
        assert corrector.correction(word) == original.correction(word)
