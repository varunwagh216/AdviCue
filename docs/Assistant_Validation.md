# Local assistant improvements

The assistant previously classified every request into a client-record view. It now separates conceptual explanations and drafting from record searches. Arithmetic still uses scoped database queries; no model-generated SQL is executed. Deterministic calculations bypass the generative router.

Common SIP and return-method explanations, import help, advice-outcome guidance and basic meeting/message drafts use shipped offline reference notes. Other explanations use the existing local llama.cpp model with a shorter prompt, bounded output and repetition control. Incomplete outputs are rejected. Market-price freshness requests explain the offline limitation.

Validation: 37 focused backend tests passed; production frontend build passed. Actual installed 1B model calls were tested. Initial testing exposed an incorrect SIP expansion and incomplete drafts, prompting the offline reference path. Final checks confirmed SIP, return comparison, import instructions and agenda responses. Open-ended quality remains uneven on this small model. No weight fine-tuning or model download was performed. These changes do not establish financial accuracy for arbitrary generated answers.

References stored with the application:
- AMFI SIP investor education: https://www.amfiindia.com/investor/become-mf-distributor?zoneName=sip
- CFA Institute performance reporting: https://blogs.cfainstitute.org/blog/2013/10/09/performance-reporting-winning-the-scoreless-game/

The application does not fetch these references during operation.
