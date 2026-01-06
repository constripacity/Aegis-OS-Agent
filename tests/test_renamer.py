

from pathlib import Path

from aegis.core.renamer import Renamer


def test_renamer_generates_unique_names(app_config, tmp_path) -> None:
    file_path = tmp_path / "example.txt"
    file_path.write_text("data", encoding="utf-8")
    renamer = Renamer(app_config)
    new_path = renamer.rename(file_path, ["report", "invoice"])
    assert new_path != file_path
    assert new_path.exists()
    assert "report" in new_path.name
    second = new_path.parent / "example.txt"
    second.write_text("data2", encoding="utf-8")
    new_second = renamer.rename(second, ["report"])
    assert new_second != new_path

