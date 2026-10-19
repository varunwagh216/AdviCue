import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, ArrowRight, BarChart3, CircleAlert, RefreshCw, Search, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, formatINR, humanError, type PatternResponse, type ScanResponse } from '../lib/api'
import { ruleName, caseReason, assetName } from '../lib/display'

export default function PatternExplorer() {
  const [names,setNames]=useState<Record<string,string>>({});useEffect(()=>{void api.get<{items:Array<{id:string;display_name:string}>}>('/investors').then(r=>setNames(Object.fromEntries(r.data.items.map(c=>[c.id,c.display_name])))).catch(()=>{})},[]);
  const [data,setData]=useState<PatternResponse|null>(null)
  const [loading,setLoading]=useState(true)
  const [scanning,setScanning]=useState(false)
  const [canScan,setCanScan]=useState(false)
  const [riskLabels,setRiskLabels]=useState<{profile_median_equity_pct:Record<string,string>;expected_risk_order_observed:boolean|null;assigned_review_candidates:string[];note:string}|null>(null)
  const [tail,setTail]=useState<{investors_ranked:number;portfolio_review_investors:number;verification_investors:number;portfolio_reviews_in_top_eight:number;portfolio_reviews_in_top_twenty:number;portfolio_reviews_outside_top_twenty:number;active_flagged_investors:number;flagged_in_top_eight:number;flagged_outside_top_twenty:number;note:string}|null>(null)
  const [behaviour,setBehaviour]=useState<{assigned_signals:Array<{type:string;description:string;investor_id:string}>;organization_bursts:Array<{asset_class:string;week_start:string;investor_count:number}>}|null>(null)
  useEffect(()=>{
    api.get<{can_run_group_scan:boolean}>('/advisor-capabilities')
      .then(r=>setCanScan(r.data.can_run_group_scan))
      .catch(()=>setCanScan(false))
  },[])
  const [error,setError]=useState<string|null>(null)
  const [notice,setNotice]=useState<string|null>(null)
  const load=useCallback(async()=>{
    setLoading(true)
    try {setData((await api.get<PatternResponse>('/patterns')).data);setError(null)}
    catch(e){setError(humanError(e))}
    finally {setLoading(false)}
  },[])
  useEffect(()=>{void load();api.get('/insights/behaviour').then(r=>setBehaviour(r.data)).catch(()=>{});
    api.get('/insights/risk-labels').then(r=>setRiskLabels(r.data)).catch(()=>{});
    api.get('/insights/long-tail').then(r=>setTail(r.data)).catch(()=>{})},[load])
  async function scan(){
    setScanning(true);setNotice(null);setError(null)
    try{
      const response=(await api.post<ScanResponse>('/patterns/run')).data
      setNotice(response.matched?`Review pattern found: ${response.member_count} investors across ${response.advisor_count} advisors.`:'Scan completed: no cohort met the minimum three-investor threshold.')
      if(response.coverage)setNotice(n=>`${n} Compared ${response.coverage!.included_count} clients on ${response.coverage!.comparison_date}; ${response.coverage!.excluded_count} excluded from this date cohort, ${response.coverage!.newer_snapshot_count} have newer observations.`)
      await load()
    }catch(e){setError(humanError(e))}
    finally{setScanning(false)}
  }
  return <div className="page-fade">
    <div className="standard-heading"><h1>Pattern detection</h1><p>Shared portfolio signals across investors.</p></div>
    {error&&<div className="error-banner" role="alert"><CircleAlert size={18}/>{error}</div>}
    {notice&&<div className="dt-notice"><ShieldCheck size={18}/>{notice}</div>}
    <div className="px-topbar panel-card"><div><strong>Portfolio pattern scan</strong><p>Compare investors with similar risk profiles.</p></div>
      {canScan ? <button className="dt-primary" onClick={scan} disabled={scanning}><RefreshCw size={16}/>{scanning?'Scanning…':'Run pattern scan'}</button>
        : <span className="px-readonly"><ShieldCheck size={15}/> Saved patterns · Client-scoped</span>}
    </div>
    {loading?<div className="panel-card dt-placeholder">Loading saved findings…</div>:!data?.items.length?<div className="panel-card dt-placeholder"><Search size={38}/><strong>No matching patterns in the latest scan</strong><span>{data?.message||'Import and validate holdings, then run a new pattern scan.'}</span></div>:
      data.items.map(pattern=><div className="panel-card px-pattern" key={pattern.id}>
        <div className="px-pattern-head"><div><h2>{ruleName(pattern.rule_id)}</h2><p>{caseReason(pattern.evidence_summary)}</p></div><span className="dt-status staged">REVIEW SIGNAL</span></div>
        <div className="px-metrics">
          <div><strong>{pattern.member_count}</strong><span>Investors in group</span></div>
          {pattern.advisor_count!==null&&<div><strong>{pattern.advisor_count}</strong><span>Source advisors represented</span></div>}
          <div><strong>{formatINR(pattern.recorded_value_total)}</strong><span>Aggregate recorded holdings</span></div>
          <div><strong>{pattern.as_of_date}</strong><span>Holdings source date</span></div>
        </div>
        <div className="px-rule-meta"><BarChart3 size={16}/> {pattern.as_of_date} · Anonymous group totals</div>
        <div className="px-review-note"><AlertTriangle size={19}/><span>{caseReason(pattern.interpretation)}</span></div>
        <details className="pattern-clients"><summary>Review these clients · {pattern.members.length} assigned matches</summary><div className="dt-list-heading"><h3>My assigned investor matches</h3><span>{pattern.members.length} matches</span></div>
        <div className="investor-table"><table><thead><tr><th>Investor</th><th>Equity</th><th>Fixed deposits</th><th>Recorded value</th><th>Source rows</th><th>Review</th></tr></thead><tbody>
          {pattern.members.map(m=><tr key={m.investor_id}><td><strong>{names[m.investor_id]||'Assigned client'}</strong></td><td>{m.equity_pct}%</td><td>{m.fixed_deposit_pct}%</td><td>{formatINR(m.recorded_value)}</td><td>{m.source_row_ids.length} holdings</td><td><Link className="px-investor-link" to={`/investors?selected=${encodeURIComponent(m.investor_id)}`}>Review client <ArrowRight size={14}/></Link></td></tr>)}
        </tbody></table></div></details><div className="advc-evidence-note"><ShieldCheck size={17}/> The group figures are anonymous aggregates. Only your assigned investors are listed or accessible.</div>
      </div>)}
    <details className="focus-disclosure panel-card focus-panel"><summary>Source-book coverage and supporting diagnostics</summary>
    {!!tail&&<div className="panel-card px-pattern"><h2>Overlooked investors</h2>
      <p><strong>{tail.portfolio_review_investors}</strong> investors have active portfolio-review cases in the {tail.investors_ranked}-investor source book. <strong>{tail.portfolio_reviews_in_top_twenty}</strong> are among the largest 20 accounts; <strong>{tail.portfolio_reviews_outside_top_twenty}</strong> rank below the largest 20 by recorded holdings.</p><p><strong>{tail.verification_investors}</strong> investors separately have data-verification cases. These are not findings of poor investment performance.</p><p className="concept-footnote">Source-book ranks use the full imported book. Your workspace shows the clients assigned to you.</p>
      
    </div>}
    {!!riskLabels&&<div className="panel-card px-pattern"><h2>Risk profile check</h2>
      
      <p>{Object.entries(riskLabels.profile_median_equity_pct).map(([k,v])=>`${k}: ${v}% median equity`).join(' · ')}</p>
      {riskLabels.expected_risk_order_observed===false&&<p className="fin-warning">The expected conservative → moderate → aggressive ordering is not observed. Verify source risk labels and mandates before any conclusions.</p>}
      {!!riskLabels.assigned_review_candidates.length&&<p>Assigned clients to verify: {riskLabels.assigned_review_candidates.join(', ')}</p>}
    </div>}
    {!!behaviour&&(behaviour.organization_bursts.length>0||behaviour.assigned_signals.length>0)&&<div className="panel-card px-pattern"><h2>Transaction signals</h2>
      {behaviour.organization_bursts.map((s,i)=><p key={`burst-${i}`}>Organization aggregate: {s.investor_count} investors redeemed {assetName(s.asset_class)} in the week starting {s.week_start}. Names are withheld.</p>)}
      {behaviour.assigned_signals.map((s,i)=><p key={`own-${i}`}>{s.investor_id}: {s.description}</p>)}
    </div>}
    
    </details>
  </div>
}
