from pathlib import Path


def build_extension_map(rules):
    ext_to_category = {}
    for rule in rules:
        for ext in rule["extensions"]:
            ext_to_category[ext.lower()] = rule["category"]
    return ext_to_category


def category_for(filename, ext_to_category):
    ext = Path(filename).suffix.lower()
    return ext_to_category.get(ext)


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
        category = category_for(entry.name, ext_to_category)
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
