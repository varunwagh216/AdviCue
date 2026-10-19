# Product experience update

Implemented the navy and teal prototype using existing advisor data and routes.

- Home: personalized greeting, text/voice search, three real next actions and first-visit guidance.
- Reviews: urgency/category, goal and review-status filters; source explanations and actual scheduled advice review dates (otherwise Not scheduled).
- Client: Overview, Portfolio & Goals, Advice & Outcomes and Meetings tabs, with keyboard navigation.
- Advice: four-stage timeline using finalized advice, task completion, review dates and evaluated outcomes; missing evidence and sample results remain explicit.
- Search: structured answer, linked record cards, evidence/scope disclosure and next actions.
- Follow-ups: Today, Upcoming, Overdue, Completed and All views, client names and separate detail routes.
- Patterns: concise findings and expandable named-client matches.
- Shared presentation: readable typography, allocation bars with percentages, values and dates, consistent controls, focus states, reduced-motion support and retry/empty feedback.
- Local AI: read-only loopback health check distinguishes Ready, Starting and Needs setup; no inference or downloads are triggered by the status check.

Validation: production TypeScript/Vite build passed; 51 backend regression checks passed; 6 desktop/mobile browser workflows passed using an isolated sample database. Browser checks cover real SIP results, evidence links, review filters, client tabs, outcome timeline, follow-up schedules, first-visit state and mobile menu. The tests do not constitute a real advisor pilot.

Login, local inference model weights, financial calculations and startup port fallback are preserved. No external assets or services were added. Models are excluded from the application ZIP; judge materials remain a separate download.
