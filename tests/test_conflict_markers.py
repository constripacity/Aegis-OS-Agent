"""Repository hygiene tests to guard against unresolved merge markers."""



from pathlib import Path
import subprocess
from typing import Iterable


CONFLICT_MARKERS: tuple[str, ...] = ("<<<<<<<", "=======", ">>>>>>>")


def _tracked_files() -> Iterable[Path]:
    output = subprocess.check_output(["git", "ls-files"], text=True)
    for line in output.splitlines():
        line = line.strip()
        if line:
            yield Path(line)


def test_repository_has_no_conflict_markers() -> None:
    offenders: list[Path] = []
    for path in _tracked_files():
        try:
            contents = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(marker in contents for marker in CONFLICT_MARKERS):
            offenders.append(path)

    assert not offenders, f"Merge markers detected in: {', '.join(str(p) for p in offenders)}"
