Automatic first launch: extract the full ZIP and run RUN_WINDOWS.bat. Missing Python 3.14 x64 is installed from python.org for the current Windows user; Python packages and local AI assets are then prepared automatically. Internet is required for first setup. React is already built, so Node.js/npm are not required. Prepared launches remain offline. Managed PCs may restrict software installation; if blocked, ask the PC owner to install Python 3.14 x64. SETUP_WINDOWS.bat remains available for manual preparation or repair.

# AdviCue AI

Download **AdviCue_AI.zip** from the latest GitHub release for the application. Download **AdviCue_AI_Judge_Materials.zip** separately for slides, the guide and sample inputs.

Extract the application into a new folder. Double-click RUN_WINDOWS.bat for automatic setup and launch, or run setup separately in VS Code:

```powershell
.\SETUP_WINDOWS.bat
.\RUN_WINDOWS.bat
```

First setup requires internet for local AI software and models. Model weights are not included. Later operation is offline. The compiled frontend is included; Node is not needed to run it.

The browser opens automatically. Port 8000 is preferred; if occupied, the launcher selects a free local port. Use the URL it opens (also saved in app-logs/OPEN_APP_URL.txt). It verifies that the responding server belongs to this launch.

Log in with **advisor@advicue.local** / **Advisor2026!**. A fictional sample book is bundled for fresh setup, so preparing the account no longer requires a release download. Existing records and passwords are preserved. CHECK_LOGIN.bat diagnoses accounts without changing data.

The older judge guide uses port 8000; use the launcher's URL if it selects another port. Keep login credentials as above. Supporting materials are distributed separately from the runnable application.

All AI processing uses local llama.cpp and whisper.cpp. Python analytics and SQLite remain local. No setup can guarantee compatibility with every Windows installation.

## Advisor experience

Home provides voice/text search and three next actions. Reviews filter by urgency, goal and status. Client workspaces have Overview, Portfolio & Goals, Advice & Outcomes and Meetings tabs. Advice timelines distinguish completed tasks from verified investment outcomes. Follow-ups have Today, Upcoming and Overdue views. A first-visit guide, accessible focus states, responsive navigation support the full workflow.

Validation details: docs/Product_Experience_Checks.md.

See **START_HERE.md** for installation, troubleshooting and the walkthrough.

## Judge walkthrough

A fresh installation includes open reviews, six pending follow-ups and two advice drafts in the fictional judging workspace. Start with Your day, open an overdue follow-up, record its outcome, and refresh Home to see the count update. Use Patterns to explore a shared portfolio concern, inspect the named clients, then switch to risk/transaction checks and book coverage. Task dates are prepared with this submission; unfinished tasks remain overdue on later dates. Existing databases are preserved, so an older working installation is not automatically reseeded.
