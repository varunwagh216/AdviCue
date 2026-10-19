# Submission checks — 19 October 2026

The release includes the built frontend, source, local Python dependency wheels, fictional judging database, Windows setup/launch scripts and current quick-start instructions. Model weights and the separate presentation materials are excluded from the application ZIP.

## Final verification

- Production TypeScript and frontend build passed.
- Backend suite: 162 passed initially; one legacy health-response assertion was updated to verify the current edition and launcher instance identity and passed on rerun. Total: 163 passing checks. Two tests skipped because their original workbook input is not bundled with public source.
- Final browser pass: 15 checks passed across navigation, review side-panel placement, client tabs, advice/follow-up routes, AI search, Pattern detail sections and mobile layouts.
- Advice-specific read-only checks covered objective types, decision/outcome details, progress evidence choices, schedule filters and exports at desktop, tablet and phone widths.
- Fresh database initialization in a separate Python environment: correct credentials accepted, wrong password rejected, 20 assigned clients, 20 clients with open reviews and six pending actions. Bundled database fingerprint matched.
- Real local llama.cpp inference returned HTTP 200 and generated the requested response.
- Real whisper.cpp transcribed the provided 26.52-second portfolio-review recording using the installed local model.
- Existing judging-preview data was preserved during the final read-only browser checks.

The full test run and clean-environment checks took place on this Windows computer. They do not establish compatibility with every judge's hardware or Windows configuration. First setup needs internet to install the local AI assets; later operation is local. Use `START_HERE.md` and the address opened by the launcher, including when port 8000 is already occupied.

Investment outcome verification depends on approved cash flows, valuations, benchmark policies and the agreed review window. Task completion and source-reported comparisons remain distinct from verified investment outcomes. Real advisor pilot value remains unmeasured.

Automatic startup preparation: RUN_WINDOWS.bat now detects missing setup and invokes Python/dependency/model preparation before launch. Python is installed per user from the official signed python.org installer when no compatible x64 Python exists. Launcher branch checks passed with setup/start side effects stubbed; a prepared installation skipped setup. PowerShell parsing passed and the installer URL returned HTTP 200. A complete installation on a Python-free physical PC was not performed.
