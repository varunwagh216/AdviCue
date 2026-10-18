"""Match an immutable agreed objective to approved evidence at exact boundaries."""
from datetime import date
from decimal import Decimal as D
from copy import deepcopy
from app.engines.evidence import PerformanceEvidence,reconcile
from app.engines.advanced import evaluate_advice_rule
from app.core.clock import advisor_day

PERFORMANCE_METRICS={'portfolio_twr_pct','active_return_pp','benchmark_linked_pct'}


def objective_review(advice,holdings,evidence,*,today=None,evidence_id=None):
    today=today or date.today();rule=advice.outcome_rule
    result={'status':'NO_MEASURABLE_OBJECTIVE','reason':'Record a measurable objective before finalizing a new advice revision.',
        'objective':rule,'expected_outcome':advice.expected_outcome,'advice_id':advice.id,'evidence_id':None,
        'note':'An observed objective and completed task do not establish trade execution or that advice caused a return.'}
    def finish(status,reason,**kwargs):return {**result,'status':status,'reason':reason,**kwargs}
    if advice.status!='APPROVED' or not advice.decided_at:return finish('ADVICE_NOT_APPROVED','Finalize advice before evaluating its objective.')
    if not rule:return result
    if rule['metric'] not in PERFORMANCE_METRICS:
        observation=evaluate_advice_rule(advice,holdings)
        if today<date.fromisoformat(rule['due_date']):return finish('PENDING_WINDOW','The allocation deadline has not arrived.',condition=observation)
        if not observation.get('deadline_verified'):return finish('DEADLINE_EVIDENCE_REQUIRED','A holding observation on the agreed deadline is required; earlier or later holdings cannot verify that deadline.',condition=observation)
        met=observation['status']=='SATISFIED_OBSERVATION'
        return finish('OBJECTIVE_MET' if met else 'OBJECTIVE_NOT_MET','Recorded deadline holdings satisfy the agreed condition.' if met else 'Recorded deadline holdings do not satisfy the agreed condition.',observed_value=observation['observed_pct'],unit='%',condition=observation,source_row_ids=observation['evidence_source_row_ids'])
    start=date.fromisoformat(rule['window_start']);end=date.fromisoformat(rule['window_end'])
    if start<=advisor_day(advice.decided_at):return finish('APPROVAL_AFTER_WINDOW','The financial measurement window must start after the advice approval date in the India business calendar. Daily valuations cannot separate intraday pre-advice activity.')
    if today<end:return finish('PENDING_WINDOW','The agreed financial measurement period has not ended.')
    rows=[r for r in evidence if r.kind=='PERFORMANCE' and r.status=='APPROVED' and (not evidence_id or r.id==evidence_id)]
    rows.sort(key=lambda r:(r.approved_at,r.id),reverse=True)
    for row in rows:
        payload=deepcopy(row.payload)
        if payload.get('client_id')!=advice.investor_id:continue
        payload['periods']=[p for p in payload['periods'] if start<=date.fromisoformat(p['start_date']) and date.fromisoformat(p['end_date'])<=end]
        if not payload['periods'] or payload['periods'][0]['start_date']!=start.isoformat() or payload['periods'][-1]['end_date']!=end.isoformat():continue
        try:calculation=reconcile(PerformanceEvidence.model_validate(payload))
        except (ValueError,ArithmeticError):continue
        value=D(calculation[rule['metric']]);target=D(str(rule['target_pct']))
        met=value>=target if rule['comparator']=='>=' else value<=target
        return finish('OBJECTIVE_MET' if met else 'OBJECTIVE_NOT_MET','The reviewed observation meets the agreed threshold.' if met else 'The reviewed observation falls short of the agreed threshold.',
            observed_value=str(value),unit='pp' if rule['metric']=='active_return_pp' else '%',evidence_id=row.id,evidence_sha256=row.payload_sha256,
            evidence_approved_at=row.approved_at.isoformat(),illustrative=payload.get('illustrative',False),window_start=start.isoformat(),window_end=end.isoformat(),calculation=calculation)
    return finish('EVIDENCE_REQUIRED','An approved client-bound performance manifest must supply exact opening and closing boundaries for the agreed window. No interpolation or unreviewed reported returns are used.')
