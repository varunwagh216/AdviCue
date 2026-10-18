import axios from 'axios'

export interface UserInfo {
  id: string
  name: string
  email: string
  role: 'ADVISOR' | 'SUPERVISOR'
}
export interface AuthResponse { user: UserInfo; csrf_token: string }
export interface HealthResponse { status: string; service: string; database: string }
export interface DashboardResponse {
  investor_count: number
  attention_count: number | null
  pattern_count: number | null
  advice_count: number | null
  open_tasks_count: number | null
  as_of: string
  latest_import?: { id: string; status: string; filename: string; warnings: number; errors: number } | null
  modules: Array<{ name: string; status: string }>
}
export interface Investor {
  id: string; display_name: string; risk_profile: string | null; advisor_id: string
  source_advisor_code: string | null; city: string | null; primary_goal: string | null
}
export interface ImportBatch {
  id:string;filename:string;status:'STAGED'|'BLOCKED'|'COMMITTED';
  created_at:string;committed_at:string|null;total_rows:number;error_count:number;warning_count:number;
  sheet_counts:Record<string,number>
}
export interface ImportIssue {
  id:string;sheet_name:string;row_number:number;field_name:string|null;
  severity:'ERROR'|'WARNING';code:string;message:string
}
export interface InvestorDetails {
  investor:{id:string;display_name:string;risk_profile:string|null;age:number|null;
    source_advisor_code:string|null;city:string|null;primary_goal:string|null;
    goal_target_amount:string|null;goal_target_date:string|null}
  holdings:Array<{holding_id:string;asset_class:string;instrument_name:string;current_value:string;as_of_date:string;source_row_id:string}>
  transaction_count:number;snapshot_count:number;performance_status:string;note:string
}

export const api = axios.create({
  // Same-origin Vite proxy: browser talks only to the frontend origin.
  // No manual localhost / 127.0.0.1 CORS coordination required.
  baseURL: '/api/v1',
  withCredentials: true,
  timeout: 12000,
  headers: { 'Content-Type': 'application/json' },
})

let csrf: string | null = null
export function setCsrf(token: string | null) { csrf = token }
api.interceptors.request.use(config => {
  if (config.method && !['get', 'head', 'options'].includes(config.method.toLowerCase()) && csrf) {
    config.headers.set('X-CSRF-Token', csrf)
  }
  return config
})

export function humanError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) return 'Cannot connect to the backend. Make sure FastAPI is running on port 8000.'
    const detail = error.response.data?.detail
    return typeof detail === 'string' ? detail : `Request failed (${error.response.status})`
  }
  return error instanceof Error ? error.message : 'An unexpected error occurred.'
}

export interface AllocationClass {
  asset_class:string; value:string; weight_pct:string|null; source_row_ids:string[]
}
export interface InvestorAnalysis {
  investor_id:string; risk_profile:string|null; currency:string
  allocation:{status:string;as_of_date:string|null;total_value:string|null;currency:string;
    equity_pct:string|null;fixed_deposit_pct:string|null;asset_classes:AllocationClass[];
    source_row_ids:string[];explanation:string}
  source_quality_issues:Array<{source_row_id:string;severity:string;code:string;message:string}>
  performance:{status:string;reason:string;source_snapshot_count:number;benchmark_status:string;
    recorded_balance_change:null|{start_date:string;end_date:string;start_value:string;end_value:string;
      recorded_value_change_pct:string|null;warning:string}}
  reported_comparison?:{status:string;reason:string;negative_months:number;observed_months:number;
    sum_monthly_gap_pp:string|null;last_three_gap_pp:string|null;
    reported_linked_portfolio_pct:string|null;reported_linked_benchmark_pct:string|null;reported_linked_gap_pp:string|null;
    months:Array<{date:string;reported_return_pct:string;reported_benchmark_pct:string;gap_pp:string;source_row_id:string}>;source_row_ids:string[]}
  gap_attribution?:{status:string;unexplained_gap_pp:string|null;note:string;contributions:Array<{asset_class:string;contribution_pp:string}>}
  source_class_return_proxy?:{status:string;unexplained_gap_pp:string|null;reported_summed_gap_pp?:string;note:string;contributions:Array<{asset_class:string;proxy_contribution_pp:string;source_references:Array<{month:string;source_reference:string;source_file_hash:string}>}>}
  review_agenda?:{agenda:string[];draft_client_message:string;note:string}
  peer_exposure?:{status:string;note:string;items:Array<{asset_class:string;client_weight_pct:string;peer_median_weight_pct:string;weight_difference_pp:string}>}
  attention_score?:{band:string;score:number;components:Record<string,string|number>;explanation:string}
  behaviour_signals?:Array<{type:string;description:string;asset_class?:string;share_pct?:string;source_row_ids:string[]}>
  data_trust_summary?:{goal_funding_verification_needed:boolean;different_date_identical_balance:boolean;ambiguous_date_rows:number}
  long_tail?:{rank_by_recorded_holdings:number|null;organization_investors:number;method:string}
  advice_outcomes?:Array<{advice_id:string;status:string;reason:string;reported_comparison?:{sum_monthly_gap_pp:string}}>
  goal:{target_amount:string|null;target_date:string|null;status:string;reason:string;
    observed_average_monthly_sip?:string|null;monthly_sip_note?:string}
  assessment:string
}
export interface GoalScenarioResult {
  investor_id:string;currency:string;as_of_date:string;target_date:string;target_amount:string;
  goal_assigned_principal:string;monthly_contribution:string;months:number;contribution_timing:string;
  disclaimer:string;scenarios:Array<{annual_assumption_pct:string;projected_value:string;
    goal_gap:string;meets_target_under_assumption:boolean}>
}
export interface Pattern {
  id:string;rule_id:string;rule_version:string;as_of_date:string;scope:string;
  member_count:number;advisor_count:number|null;recorded_value_total:string;
  assigned_member_count?:number;
  evidence_summary:string;interpretation:string;
  members:Array<{investor_id:string;equity_pct:string;fixed_deposit_pct:string;
    recorded_value:string;source_row_ids:string[]}>
}
export interface PatternResponse { items:Pattern[];
  latest_run:{id:string;as_of_date:string|null;rule_version:string;created_at:string}|null;
  message:string }
export interface ScanResponse {run_id:string;as_of_date:string|null;matched:boolean;
  coverage?:{included_count:number;excluded_count:number;newer_snapshot_count:number;comparison_date:string;policy:string};
  pattern_id:string|null;member_count:number;advisor_count:number;recorded_value_total:string;message:string}
export const formatINR = (amount:string|null|undefined) =>
  amount===null || amount===undefined ? 'Not available' :
  `₹${Number(amount).toLocaleString('en-IN',{minimumFractionDigits:0,maximumFractionDigits:2})}`

export interface AttentionCase {
  id:string; investor_id:string; advisor_id:string; pattern_id:string|null;
  rule_id:string; rule_version:string; source_date:string;
  priority:'P1'|'P2'|'P3'|'V_VERIFY';
  status:'OPEN'|'IN_REVIEW'|'NEEDS_DATA'|'RESOLVED';
  superseded_by_id:string|null;
  investor_name?:string; ranking?:{score:number;evaluated_on:string;source_age_days:number;stale_source:boolean;overdue_tasks:number;due_soon_tasks:number;due_advice_reviews:number;obligation_points:number;components:Record<string,string|number>;explanation:string};
  title:string;reason:string;suggested_action:string;
  evidence_source_row_ids:string[];created_at:string;updated_at:string;
  resolved_at:string|null;resolution_note:string|null;data_note:string;
}
export interface AttentionResponse {
  items:AttentionCase[];total_visible:number;
  counts:Record<'OPEN'|'IN_REVIEW'|'NEEDS_DATA'|'RESOLVED',number>;
  note:string
}
export interface AdviceRecord {
  id:string;investor_id:string;investor_name?:string;advisor_id:string;alert_id:string;
  outcome_rule?:{metric:string;comparator:string;target_pct:number;due_date:string;window_start?:string;window_end?:string}|null;
  status:'DRAFT'|'SUBMITTED'|'APPROVED'|'REJECTED';
  recommendation:string;rationale:string;assumptions:string|null;
  evidence_source_row_ids:string[];created_at:string;submitted_at:string|null;
  decided_at:string|null;decided_by:string|null;decision_note:string|null;
  supersedes_id:string|null;source_meeting_id:string|null;expected_outcome?:string|null;review_date?:string|null;review_trigger?:string|null
}
export interface FollowUpTask {
  id:string;investor_id:string;investor_name?:string;advice_id:string|null;source_meeting_id?:string|null;owner_id:string;
  title:string;due_date:string;status:'OPEN'|'IN_PROGRESS'|'DONE'|'CANNOT_VERIFY';
  display_status:string;completion_note:string|null;
  evidence_type:'ADVISOR_ATTESTATION'|'SOURCE_REFERENCE'|null;
  evidence_reference:string|null;created_at:string;updated_at:string;completed_at:string|null
}
export interface AuditItem {action:string;entity_type:string|null;entity_id:string|null;created_at:string}
