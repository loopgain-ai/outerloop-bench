"""Test suite for textstats. THE TESTS ARE THE SPEC — do not modify this file."""

import pytest

from textstats import (
    WordCounter,
    median,
    moving_average,
    normalize_whitespace,
    parse_duration,
    percentile,
    sentence_split,
    slugify,
    top_k_words,
    word_count,
)


# --- normalize_whitespace ---

def test_normalize_simple():
    assert normalize_whitespace("a b") == "a b"

def test_normalize_double_spaces():
    assert normalize_whitespace("a  b") == "a b"

def test_normalize_many_spaces():
    assert normalize_whitespace("a     b") == "a b"

def test_normalize_tabs_and_newlines():
    assert normalize_whitespace("a\t b\n\nc") == "a b c"

def test_normalize_strips_ends():
    assert normalize_whitespace("  a b  ") == "a b"


# --- sentence_split ---

def test_sentences_periods():
    assert sentence_split("One. Two. Three.") == ["One", "Two", "Three"]

def test_sentences_question():
    assert sentence_split("Really? Yes. Sure!") == ["Really", "Yes", "Sure"]

def test_sentences_single():
    assert sentence_split("Just one sentence") == ["Just one sentence"]

def test_sentences_empty():
    assert sentence_split("") == []


# --- word_count ---

def test_word_count_basic():
    assert word_count("the quick brown fox") == 4

def test_word_count_empty():
    assert word_count("") == 0


# --- top_k_words ---

def test_top_k_basic():
    assert top_k_words("a a a b b c", 2) == ["a", "b"]

def test_top_k_case_insensitive():
    assert top_k_words("Dog dog DOG cat cat", 2) == ["dog", "cat"]

def test_top_k_tie_alphabetical():
    assert top_k_words("pear apple pear apple mango", 3) == ["apple", "pear", "mango"]


# --- median ---

def test_median_odd():
    assert median([3, 1, 2]) == 2

def test_median_even():
    assert median([4, 1, 3, 2]) == 2.5

def test_median_even_floats():
    assert median([1.0, 2.0]) == 1.5

def test_median_empty_raises():
    with pytest.raises(ValueError):
        median([])


# --- moving_average ---

def test_moving_average_basic():
    assert moving_average([1, 2, 3, 4], 2) == [1.5, 2.5, 3.5]

def test_moving_average_full_window():
    assert moving_average([1, 2, 3], 3) == [2.0]

def test_moving_average_window_one():
    assert moving_average([5, 7], 1) == [5.0, 7.0]

def test_moving_average_bad_window():
    with pytest.raises(ValueError):
        moving_average([1, 2], 0)


# --- percentile ---

def test_percentile_min_max():
    assert percentile([1, 2, 3, 4], 0) == 1
    assert percentile([1, 2, 3, 4], 100) == 4

def test_percentile_interpolates():
    assert percentile([1, 2, 3, 4], 50) == 2.5

def test_percentile_quarter():
    assert percentile([10, 20, 30, 40, 50], 25) == 20

def test_percentile_interp_uneven():
    assert percentile([0, 10], 75) == 7.5


# --- slugify ---

def test_slugify_basic():
    assert slugify("Hello World") == "hello-world"

def test_slugify_punctuation_runs():
    assert slugify("rock & roll!!") == "rock-roll"

def test_slugify_no_edge_hyphens():
    assert slugify("  spaced out  ") == "spaced-out"


# --- parse_duration ---

def test_duration_hours():
    assert parse_duration("2h") == 120

def test_duration_minutes():
    assert parse_duration("45m") == 45

def test_duration_combined():
    assert parse_duration("1h30m") == 90

def test_duration_invalid():
    with pytest.raises(ValueError):
        parse_duration("soon")


# --- WordCounter ---

def test_wordcounter_counts():
    wc = WordCounter()
    wc.add("a b a")
    assert wc.most_common() == [("a", 2), ("b", 1)]

def test_wordcounter_instances_independent():
    wc1 = WordCounter()
    wc1.add("hello hello")
    wc2 = WordCounter()
    assert wc2.most_common() == []

def test_wordcounter_tie_alphabetical():
    wc = WordCounter()
    wc.add("beta alpha")
    assert wc.most_common() == [("alpha", 1), ("beta", 1)]
