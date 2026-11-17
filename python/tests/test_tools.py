"""Where the engine finds poppler and tesseract: its own environment first
(a conda-forge environment carries both), then the system's."""

import os
import stat
import sys

from extract_text import documents


def _fake_program(folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def test_the_environments_own_copy_is_found_first(tmp_path, monkeypatch):
    own = _fake_program(tmp_path / "env" / "bin", "pdftotext")
    system = _fake_program(tmp_path / "system", "pdftotext")
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "env"))
    monkeypatch.setenv("PATH", str(system.parent))
    assert documents.tool_path("pdftotext") == str(own)
    assert documents.tool_is_own("pdftotext")


def test_the_systems_copy_is_used_when_the_environment_has_none(tmp_path, monkeypatch):
    system = _fake_program(tmp_path / "system", "pdftotext")
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "env"))
    monkeypatch.setenv("PATH", str(system.parent))
    assert documents.tool_path("pdftotext") == str(system)
    assert not documents.tool_is_own("pdftotext")
    assert documents.tool_path("no-such-program-here") is None
    assert not documents.have("no-such-program-here")


def test_own_tesseract_is_told_where_its_language_data_is(tmp_path, monkeypatch):
    _fake_program(tmp_path / "env" / "bin", "tesseract")
    data = tmp_path / "env" / "share" / "tessdata"
    data.mkdir(parents=True)
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "env"))
    monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
    assert documents._tool_env("tesseract")["TESSDATA_PREFIX"] == str(data)
    # only tesseract needs it, and a setting the user made is left alone
    assert documents._tool_env("pdftotext") is None
    monkeypatch.setenv("TESSDATA_PREFIX", "/somewhere/the/user/chose")
    assert documents._tool_env("tesseract") is None


def test_a_helper_programs_stray_bytes_do_not_stop_the_read(tmp_path):
    # a program that writes bytes that are not text to its error stream
    script = tmp_path / "noisy.py"
    script.write_text("import sys\nsys.stderr.buffer.write(b'\\x89PNG\\xff')\nprint('ok')\n")
    r = documents.run([sys.executable, str(script)])
    assert r.stdout.strip() == "ok"
    assert os.fspath(script)  # the call returned instead of raising
