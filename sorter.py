import re
from pathlib import Path

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_LETTER_DIGIT = re.compile(r"(?<=[a-z])(?=[0-9])|(?<=[0-9])(?=[a-z])")


def build_extension_map(rules):
    ext_to_category = {}
    for rule in rules:
        for ext in rule["extensions"]:
            ext_to_category[ext.lower()] = rule["category"]
    return ext_to_category


def normalize(text):
    """Lowercase, split letter/digit runs apart, turn every run of non-alphanumerics
    into a single space, and pad with spaces so keyword lookups match whole words
    only. "CHEM135_HW-3.pdf" stem becomes " chem 135 hw 3 ", so " hw " and " chem "
    hit while "shwoop" and "classic" don't. Keywords go through the same function,
    so "w-2" and "pset" match "W2" and "PSET2" respectively."""
    text = _LETTER_DIGIT.sub(" ", text.lower())
    return f" {_NON_ALNUM.sub(' ', text).strip()} "


def build_name_matchers(name_rules):
    """[(category, [normalized keyword, ...], [compiled pattern, ...],
    match_any_extension), ...] in priority order - the first rule that matches a
    filename wins. Patterns are regexes run against the SAME normalized string the
    keywords are, so they see " 141 f 26 2 solidsofrev ", not the raw filename."""
    matchers = []
    for rule in name_rules or []:
        keywords = [normalize(k) for k in rule.get("keywords", [])]
        patterns = [re.compile(p) for p in rule.get("patterns", [])]
        matchers.append(
            (
                rule["category"],
                keywords,
                patterns,
                bool(rule.get("match_any_extension", False)),
            )
        )
    return matchers


def category_for(filename, ext_to_category, name_matchers=()):
    """Keyword rules take precedence over extension rules. A keyword rule only
    claims a file whose extension is otherwise sortable, unless that rule sets
    match_any_extension."""
    ext = Path(filename).suffix.lower()
    ext_category = ext_to_category.get(ext)
    haystack = normalize(Path(filename).stem)
    for category, keywords, patterns, match_any_extension in name_matchers:
        if ext_category is None and not match_any_extension:
            continue
        if any(keyword in haystack for keyword in keywords):
            return category
        if any(pattern.search(haystack) for pattern in patterns):
            return category
    return ext_category


def is_ignored(filename, ignored_extensions, skip_names):
    if filename in skip_names:
        return True
    ext = Path(filename).suffix.lower()
    return ext in {e.lower() for e in ignored_extensions}


def dest_path(watch_folder, category, filename):
    """Destination folder + collision-safe destination file path."""
    dest_dir = Path(watch_folder) / category
    dest = dest_dir / filename
    if dest.exists():
        stem, suffix = Path(filename).stem, Path(filename).suffix
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{stem} ({counter}){suffix}"
            counter += 1
    return dest_dir, dest


class StabilityTracker:
    """Tracks file sizes across polls; a file is 'stable' (finished downloading,
    safe to move) once its size hasn't changed for `required_checks` consecutive
    polls in a row."""

    def __init__(self, required_checks=2):
        self.required_checks = max(1, required_checks)
        self._history = {}  # path_str -> (last_size, consecutive_unchanged_count)

    def observe(self, path, size):
        path_str = str(path)
        last_size, count = self._history.get(path_str, (None, 0))
        count = count + 1 if last_size == size else 1
        self._history[path_str] = (size, count)
        return count >= self.required_checks

    def forget(self, path):
        self._history.pop(str(path), None)

    def prune(self, existing_paths):
        existing = {str(p) for p in existing_paths}
        for key in list(self._history.keys()):
            if key not in existing:
                del self._history[key]


def find_ready_to_sort(watch_folder, config, tracker):
    """Scans watch_folder (non-recursive) and returns [(src, dest_dir, dest, category), ...]
    for files whose extension matches a rule and whose size has been stable for
    `stability_checks` consecutive polls."""
    watch_path = Path(watch_folder)
    ext_to_category = build_extension_map(config["rules"])
    name_matchers = build_name_matchers(config.get("name_rules", []))
    ignored_extensions = config.get("ignored_extensions", [])
    skip_names = set(config.get("skip_names", []))

    ready = []
    current_files = []
    try:
        entries = list(watch_path.iterdir())
    except OSError:
        return ready

    for entry in entries:
        if not entry.is_file():
            continue
        if is_ignored(entry.name, ignored_extensions, skip_names):
            continue
        category = category_for(entry.name, ext_to_category, name_matchers)
        if category is None:
            continue
        current_files.append(entry)
        try:
            size = entry.stat().st_size
        except OSError:
            continue
        if tracker.observe(entry, size):
            dest_dir, dest = dest_path(watch_folder, category, entry.name)
            ready.append((entry, dest_dir, dest, category))

    tracker.prune(current_files)
    return ready
