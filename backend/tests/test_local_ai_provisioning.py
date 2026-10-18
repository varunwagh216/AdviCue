"""Offline launch contract; missing assets never trigger a download."""
from pathlib import Path
from app.scripts import prepare_whisper

def test_whisper_checker_fails_when_assets_missing(monkeypatch,tmp_path):
    monkeypatch.setattr(prepare_whisper,'speech_assets',lambda:(tmp_path/'missing.exe',tmp_path/'missing.bin'))
    monkeypatch.setattr('sys.argv',['prepare_whisper','--check'])
    assert prepare_whisper.main()==1

def test_whisper_checker_recognizes_local_assets(monkeypatch,tmp_path):
    exe=tmp_path/'whisper-cli';model=tmp_path/'ggml-base.bin';exe.write_bytes(b'runtime');model.write_bytes(b'model')
    monkeypatch.setattr(prepare_whisper,'speech_assets',lambda:(exe,model))
    monkeypatch.setattr('sys.argv',['prepare_whisper','--check'])
    assert prepare_whisper.main()==0

def test_startup_never_provisions_dependencies_or_models():
    root=Path(__file__).resolve().parents[2]
    start=(root/'scripts/START_WINDOWS.ps1').read_text(encoding='utf-8')
    ensure=(root/'scripts/ENSURE_LOCAL_AI.ps1').read_text(encoding='utf-8')
    assert 'pip install' not in start and 'npm' not in start and 'SETUP_WINDOWS.ps1' not in start
    assert "'PREPARE_LLAMA_CPP.ps1') -OfflineOnly" in ensure
    assert '--download' not in ensure and 'pip install' not in ensure and '--check' in ensure
    assert 'seed_showcase_examples' not in start and 'seed_judge_demo' not in start

def test_offline_install_has_no_index_fallback():
    setup=(Path(__file__).resolve().parents[2]/'scripts/SETUP_WINDOWS.ps1').read_text(encoding='utf-8')
    assert '--no-index --find-links $wheels' in setup
