from pathlib import Path


def find_files(directory: Path) -> list[Path]:
    """Return every non-hidden file under directory, recursively, sorted by path."""
    if not directory.is_dir():
        raise NotADirectoryError(directory)
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file()
        and not any(part.startswith(".") for part in path.relative_to(directory).parts)
    )
