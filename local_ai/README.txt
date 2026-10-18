AdviCue AI local assets — Built with Llama

Text: local_ai/bin/llama-server.exe and neighboring DLLs
Model: local_ai/models/Llama-3.2-1B-Instruct-Q4_K_M.gguf
Speech: local_ai/whisper/whisper-cli.exe and neighboring DLLs
Model: local_ai/models/ggml-base.bin

The complete offline Windows bundle includes these files. Normal startup only
checks local assets; it never installs packages, downloads weights, or calls a
cloud AI service. Keep the llama.cpp and whisper.cpp DLL directories separate.
The smaller source archive excludes model weights and executables.

Python 3.14 / 3.12 Windows dependency wheels are in offline-wheels.
Use SETUP_WINDOWS.bat to install them without accessing package indexes.
The compiled React app is served by FastAPI; Node is only needed to rebuild it.

Standard 16-bit mono/stereo PCM WAV is normalized locally in Python. Compressed
meeting audio requires a preinstalled local FFmpeg executable; it is optional
and is not included. Browser voice search captures PCM WAV directly.

llama.cpp b11429, whisper.cpp v1.7.6. Model: Llama 3.2 1B Instruct,
Q4_K_M quantization by bartowski. Speech: multilingual Whisper base GGML.
See local_ai/licenses for MIT, Meta Llama license and acceptable-use notices.
