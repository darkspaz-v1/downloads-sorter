import json
from pathlib import Path

import pytest

from sorter import (
    StabilityTracker,
    build_extension_map,
    build_name_matchers,
    category_for,
    dest_path,
    find_ready_to_sort,
    is_ignored,
    normalize,
)

CONFIG = json.loads((Path(__file__).resolve().parent.parent / "config.json").read_text(encoding="utf-8"))
EXT = build_extension_map(CONFIG["rules"])
NAMES = build_name_matchers(CONFIG["name_rules"])


def cat(filename):
    return category_for(filename, EXT, NAMES)


# --- type-folder mapping -------------------------------------------------

@pytest.mark.parametrize(
    "filename, expected",
    [
        ("photo.jpg", "Images"),
        ("PHOTO.JPEG", "Images"),  # extension match is case-insensitive
        ("vacation.heic", "Images"),
        ("bundle.tar.gz", "Archives"),
        ("setup.exe", "Installers"),
        ("clip.mkv", "Videos"),
        ("song.flac", "Audio"),
        ("report.pdf", "Documents"),
        ("mystery.xyz", None),  # unknown extension is left alone
        ("no_extension", None),
    ],
)
def test_type_folder_mapping(filename, expected):
    assert cat(filename) == expected


def test_extension_map_is_lowercase_and_covers_every_rule():
    assert EXT[".pdf"] == "Documents"
    assert all(k == k.lower() for k in EXT)
    assert set(EXT.values()) == {r["category"] for r in CONFIG["rules"]}


# --- whole-word School / Important rules ---------------------------------

@pytest.mark.parametrize(
    "filename, expected",
    [
        ("CHEM135_HW-3.pdf", "School"),
        ("hw3.pdf", "School"),  # letter/digit runs are split, so 'hw' is a whole word
        ("Syllabus.docx", "School"),
        ("Lab Report 2.docx", "School"),
        ("2024 tax return.pdf", "Important"),
        ("W-2 2024.pdf", "Important"),
        ("W2.pdf", "Important"),  # 'w-2' normalizes to 'w 2', same as 'W2'
        ("lease agreement.pdf", "Important"),
    ],
)
def test_name_rules_match_whole_words(filename, expected):
    assert cat(filename) == expected


@pytest.mark.parametrize(
    "filename",
    [
        "classic_photo.jpg",  # contains 'class' but is not the word 'class'
        "shwoop.pdf",  # contains 'hw'
        "taxidermy.png",  # contains 'tax'
        "cvsx.png",  # contains 'cv'
    ],
)
def test_keywords_do_not_match_inside_longer_words(filename):
    assert cat(filename) == EXT[Path(filename).suffix]


def test_important_outranks_school_when_both_match():
    # rules are checked in order and the first match wins
    assert cat("lecture notes tax.pdf") == "Important"
    assert cat("lecture notes.pdf") == "School"


def test_name_rule_needs_a_sortable_extension_unless_match_any_extension():
    rules = [{"category": "Important", "keywords": ["tax"]}]
    matchers = build_name_matchers(rules)
    assert category_for("tax.xyz", EXT, matchers) is None
    assert category_for("tax.pdf", EXT, matchers) == "Important"
    rules[0]["match_any_extension"] = True
    assert category_for("tax.xyz", EXT, build_name_matchers(rules)) == "Important"


def test_normalize_splits_letters_digits_and_punctuation():
    assert normalize("CHEM135_HW-3") == " chem 135 hw 3 "
    assert normalize("w-2") == normalize("W2") == " w 2 "


# --- semester / course regexes -------------------------------------------

@pytest.mark.parametrize(
    "filename",
    [
        "Solids of Rev F26.pdf",  # semester tag: 'f 26' after normalization
        "review Spring 25 packet.pdf",
        "engl 101 reading.pdf",  # course code that is NOT in the keyword list
        "hist210 reader.pdf",
        "geol 100 map.png",
    ],
)
def test_semester_and_course_patterns_classify_as_school(filename):
    assert cat(filename) == "School"


def test_semester_pattern_requires_two_digit_year_and_course_pattern_three_digits():
    # '2024' is not '19'/'2x' followed by a space, and 'engl 10' has only two digits.
    assert cat("holiday summer 2024 pics.jpg") == "Images"
    assert cat("engl 10 pics.jpg") == "Images"


# --- ignored files --------------------------------------------------------

def test_is_ignored_extensions_and_names():
    ign = CONFIG["ignored_extensions"]
    skip = set(CONFIG["skip_names"])
    assert is_ignored("movie.mp4.crdownload", ign, skip)
    assert is_ignored("A.TMP", ign, skip)
    assert is_ignored("desktop.ini", ign, skip)
    assert not is_ignored("movie.mp4", ign, skip)


# --- stable-file detection ------------------------------------------------

def test_tracker_requires_consecutive_unchanged_polls():
    t = StabilityTracker(required_checks=2)
    assert t.observe("f", 100) is False  # first sighting
    assert t.observe("f", 100) is True  # unchanged once
    t2 = StabilityTracker(required_checks=3)
    assert [t2.observe("f", 5) for _ in range(3)] == [False, False, True]


def test_tracker_growth_resets_the_count():
    t = StabilityTracker(required_checks=2)
    t.observe("f", 100)
    assert t.observe("f", 150) is False  # still downloading
    assert t.observe("f", 200) is False
    assert t.observe("f", 200) is True


def test_tracker_forget_and_prune():
    t = StabilityTracker(required_checks=2)
    t.observe("a", 1)
    t.observe("b", 1)
    t.prune(["a"])
    assert t.observe("b", 1) is False  # b was pruned, so history restarted
    assert t.observe("a", 1) is True
    t.forget("a")
    assert t.observe("a", 1) is False


def test_tracker_minimum_is_one_check():
    assert StabilityTracker(required_checks=0).observe("f", 1) is True


def make_config(**kw):
    cfg = dict(CONFIG)
    cfg.update(kw)
    return cfg


def test_find_ready_waits_for_stable_size_and_skips_ignored(tmp_path):
    (tmp_path / "done.pdf").write_bytes(b"x" * 10)
    (tmp_path / "half.mp4.crdownload").write_bytes(b"x")
    (tmp_path / "desktop.ini").write_text("x")
    (tmp_path / "unknown.xyz").write_text("x")
    (tmp_path / "subfolder").mkdir()
    tracker = StabilityTracker(required_checks=2)

    assert find_ready_to_sort(tmp_path, CONFIG, tracker) == []  # first poll: nothing is stable yet
    ready = find_ready_to_sort(tmp_path, CONFIG, tracker)  # second poll
    assert [(r[0].name, r[3]) for r in ready] == [("done.pdf", "Documents")]
    assert ready[0][2] == tmp_path / "Documents" / "done.pdf"


def test_find_ready_does_not_return_a_file_that_is_still_growing(tmp_path):
    f = tmp_path / "big.zip"
    f.write_bytes(b"x" * 10)
    tracker = StabilityTracker(required_checks=2)
    find_ready_to_sort(tmp_path, CONFIG, tracker)
    f.write_bytes(b"x" * 20)  # the browser wrote more
    assert find_ready_to_sort(tmp_path, CONFIG, tracker) == []
    assert len(find_ready_to_sort(tmp_path, CONFIG, tracker)) == 1


def test_find_ready_missing_folder_returns_empty(tmp_path):
    assert find_ready_to_sort(tmp_path / "nope", CONFIG, StabilityTracker()) == []


def test_dest_path_avoids_collisions(tmp_path):
    (tmp_path / "Documents").mkdir()
    (tmp_path / "Documents" / "a.pdf").write_text("1")
    (tmp_path / "Documents" / "a (1).pdf").write_text("2")
    dest_dir, dest = dest_path(tmp_path, "Documents", "a.pdf")
    assert dest_dir == tmp_path / "Documents"
    assert dest.name == "a (2).pdf"
    assert dest_path(tmp_path, "Documents", "fresh.pdf")[1].name == "fresh.pdf"
