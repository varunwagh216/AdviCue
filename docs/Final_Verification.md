# Final submission verification — 19 October 2026

## Results
- Full backend suite: 176 passed, 2 skipped, 1 warning (199 seconds). The skipped checks require the original workbook, which is absent from the public source.
- Browser workflow and layout suite: 15 passed (45 seconds).
- TypeScript and Vite production build: passed.
- ZIP: archive integrity, source file correspondence, SQLite integrity and foreign keys, and compiled asset references passed. No model weights, native executables, .env, virtual environment, node_modules or submission-materials directory were included.
- Extracted ZIP: all Python requirements installed into an empty Python 3.14 environment from bundled wheels with --no-index. No package download was used.
- Extracted application: successful startup while port 8000 was occupied, using an automatically chosen local port. Correct judge credentials accepted; incorrect password rejected; frontend served successfully. Startup verification used the clean test environment path and suppressed browser opening; local AI preparation was tested separately.
- Fresh database: 20 assigned clients, 20 clients with open reviews, 6 pending actions; seed fingerprint matched.
- Installed local llama.cpp and whisper.cpp: real text inference and WAV transcription passed.
- All PowerShell startup scripts parsed successfully.

## Operation
Extract AdviCue_AI.zip and double-click RUN_WINDOWS.bat. First preparation needs internet to obtain missing Python and local AI assets. React is prebuilt and does not require Node.js on judges’ PCs. Use the browser URL opened by the launcher; do not assume port 8000 when another application uses it.

Judge login: advisor@advicue.local / Advisor2026!

## Limits
This is verification on this Windows machine with isolated environments, not a guarantee for every PC. Automatic Python installation on a completely Python-free PC remains untested end to end. First-time model downloads can be affected by internet access, antivirus and machine restrictions. Model files are intentionally excluded. The installed 1B model has uneven open-ended answer quality; reference-backed answers and scoped calculations improve reliability but do not constitute weight training or verified investment advice.
