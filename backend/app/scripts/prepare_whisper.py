"""Check preinstalled whisper.cpp assets without network access."""
import argparse
from app.ai.speech import speech_assets

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check',action='store_true',required=True)
    p.parse_args()
    exe,model=speech_assets()
    if not exe.is_file() or not model.is_file():
        print('whisper.cpp unavailable. Install whisper-cli and ggml-base.bin locally first. No download attempted.')
        return 1
    print('whisper.cpp executable and model present; no network access requested.')
    return 0

if __name__=='__main__':raise SystemExit(main())
