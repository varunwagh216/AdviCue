# AdviCue AI — Start here

AdviCue helps an advisor decide which clients need attention, understand the supporting evidence, and follow agreed advice through to review.

## Install and open

1. Install Python **3.14 x64 or 3.12 x64** on Windows. Keep the Python launcher enabled.
2. Extract **AdviCue_AI.zip** fully into a new folder. Open the extracted `AdviCue_AI` folder in VS Code, or use File Explorer.
3. Run **SETUP_WINDOWS.bat** once. Internet is required to prepare the local AI software and models. Wait for setup to finish.
4. Run **RUN_WINDOWS.bat**. Use the browser address it opens. If port 8000 is occupied, the launcher chooses another free port automatically.
5. Sign in with **advisor@advicue.local** and **Advisor2026!**.

Model weights are excluded from this download. After setup, AI inference and speech transcription run locally; application operation does not require internet. The built frontend and Python dependency wheels are included, so Node.js is not required to run the release.

## Five-minute walkthrough

1. **Home:** inspect Your day and ask “How many clients have SIPs?” Open the supporting client records. The answer refers to recorded transactions, rather than verified active mandates.
2. **Reviews:** select a client and read what changed and why it matters. Open the client workspace.
3. **Client workspace:** explore Portfolio & Goals and Advice & Outcomes. Inspect the agreed objective, review window and available evidence. Missing evidence remains visible.
4. **Patterns:** inspect a shared concern, expand the matched clients and comparison method, then explore risk/transaction checks and book coverage.
5. **Advice:** open a draft or agreed recommendation. Follow-ups shows Today, Upcoming, Overdue and Completed actions. Open an action to record progress and evidence. Saving changes the local book.
6. **Ask AI:** explore Client briefs and Meetings. A local model generates new briefs; meeting notes and speech processing remain on this computer. Review generated notes before approving them.
7. **Data:** inspect source imports and validation findings. Imports require an explicit review and confirmation.

The judging workspace contains fictional investor records, 20 assigned clients, open reviews, two advice drafts and six pending actions at preparation. Prepared dates remain fixed; unfinished actions become overdue as time passes. Existing user databases are preserved and are not automatically replaced by this judging book. Follow-up completion records an action; it does not establish an investment outcome.

## If something needs attention

- **Page does not open:** read `app-logs/OPEN_APP_URL.txt` and open that address. Check `app-logs/backend.stderr.log` if startup reports a failure.
- **Login fails:** run `CHECK_LOGIN.bat` and read its diagnosis. An existing installation may have different credentials; setup preserves existing passwords.
- **AI or voice needs setup:** complete `SETUP_WINDOWS.bat`, then restart with `RUN_WINDOWS.bat`. AI models can take time to load; speed depends on the computer.
- **Older guide mentions a fixed port:** follow this document and the launcher address.

Download **AdviCue_AI_Judge_Materials.zip** separately for the presentation, detailed guide and input files. The application ZIP contains the runnable project without that materials folder.
