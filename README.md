# AdviCue AI

## Download the runnable submission

Judges should download **AdviCue_AI.zip** and the **Judges Setup and Run Guide** from [Releases](https://github.com/varunwagh216/AdviCue/releases), then extract the ZIP and follow the guide.

This source repository deliberately excludes local SQLite databases, secrets, installed environments and downloaded model runtimes/weights. The release ZIP contains the supplied sample SQLite book; a source clone alone does not contain that database. Do not upload real investor records. To run a clone, first copy the sample `backend/advicue.db` from the release ZIP, then follow the setup instructions below. The included compiled frontend and offline Python wheels are retained for reproducibility.


A private advisor workspace with local AI text and voice search, client reviews, portfolio analysis, pattern detection, advice outcome reviews and follow-ups.

## Setup and run

Python **3.14 x64** must already be installed. Python 3.12 x64 is also supported. Extract this ZIP, open the **AdviCue_AI** folder in VS Code and open its terminal:

```powershell
.\SETUP_WINDOWS.bat
.\RUN_WINDOWS.bat
```

The first setup installs Python dependencies from the included local wheels and downloads llama.cpp, the Llama text model, whisper.cpp and the speech model. Keep internet connected until setup completes. **Model files are not included in this ZIP.** The compiled frontend is included; Node.js is only needed to edit and rebuild it.

After setup, normal operation is offline. For later launches, run only:

```powershell
.\RUN_WINDOWS.bat
```

Close the backend from an older AdviCue installation if it uses port 8000. Keep your existing database backed up; this extracted folder has its own supplied SQLite database.

Open **http://127.0.0.1:8000**. Sign in with **advisor@advicue.local** / **Advisor2026!**.

## Home search

Type a question or click the microphone beside the search arrow. Speak, click Stop, review the locally generated transcript, then search. Cancel stops capture without submitting audio. Search recordings are temporary and do not become meeting notes.

Try “How many profiles have SIPs?”, “Show moderate clients”, “Which clients have equity above 60%?”, “Where does Sanya Malhotra stand?” or “Show my completed follow-ups”. Unsupported filters request clarification.

The supplied book has 20 assigned clients. SIP counts use distinct clients with qualifying positive recorded contributions. They do not establish active mandates or future monthly obligations. Holdings use dated source snapshots. Sample-source provenance and evidence limits remain clear.

## Local processing

React and TypeScript run in the browser. FastAPI retrieves locally stored SQLite records. Python calculates financial facts, llama.cpp interprets searches and drafts grounded explanations, and whisper.cpp transcribes speech locally. Normal startup does not download assets. No cloud AI endpoints, browser cloud speech recognition, CDN assets or application telemetry are used.

Standard 16-bit PCM WAV meeting recordings are normalized locally. Compressed meeting audio requires an optional preinstalled local FFmpeg executable. Browser voice capture needs no FFmpeg. Logs are in app-logs and local-ai-logs.

## Readability and verification

The existing font family and heading scale are preserved. Smaller labels, supporting notes, badges and chart text are enlarged. Desktop and mobile readability checks and the production build passed. Regression tests, actual local AI checks and the isolated 200-client synthetic-book results are in docs/. Synthetic testing does not substitute for real provider-source review or an advisor pilot.

Built with Llama. Runtime and model license notices are in local_ai/licenses/.
