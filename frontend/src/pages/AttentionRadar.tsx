import { RingChart } from '../components/ConceptCharts'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowRight, CircleAlert, CircleCheck, ClipboardList, Eye, Filter, RefreshCw, Search, ShieldCheck, TriangleAlert } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { api, humanError, type AttentionCase, type AttentionResponse } from '../lib/api'
import { caseReason, caseScore, caseSummary, priorityName, ruleName } from '../lib/display'

type Action = 'START_REVIEW'|'REQUEST_DATA'|'RESOLVE'|'REOPEN'
const statusLabel: Record<AttentionCase['status'],string> = {
  OPEN:'Open',IN_REVIEW:'In review',NEEDS_DATA:'Awaiting evidence',RESOLVED:'Resolved',
}
const actionName:Record<Action,string>={
  START_REVIEW:'Start review',REQUEST_DATA:'Request missing information',RESOLVE:'Resolve review',REOPEN:'Reopen case'
}

export default function AttentionRadar() {
  const {user}=useAuth()
  const [params]=useSearchParams()
  const [manual,setManual]=useState(false)
  const [clients,setClients]=useState<Array<{id:string;display_name:string}>>([])
  const [clientId,setClientId]=useState('')
  const [manualTitle,setManualTitle]=useState('')
  const [manualReason,setManualReason]=useState('')
  useEffect(()=>{api.get('/investors').then(r=>setClients(r.data.items)).catch(e=>setError(humanError(e)))},[])
  async function createReview(e:React.FormEvent){
    e.preventDefault();setSending(true);setError(null)
    try{const r=await api.post('/attention',{investor_id:clientId,title:manualTitle,reason:manualReason});setManual(false);setManualTitle('');setManualReason('');await load();setSelected(r.data.id);setNotice('Review created. You can now record advice for this client.')}
    catch(e){setError(humanError(e))}finally{setSending(false)}
  }
  const [data,setData]=useState<AttentionResponse|null>(null)
  const [loading,setLoading]=useState(true)
  const [sending,setSending]=useState(false)
  const [error,setError]=useState<string|null>(null)
  const [notice,setNotice]=useState<string|null>(null)
  const [status,setStatus]=useState('ACTIVE')
  const [search,setSearch]=useState('')
  const [showHistory,setShowHistory]=useState(false)
  const [selected,setSelected]=useState<string|null>(params.get('selected'))
  const [action,setAction]=useState<Action|null>(null)
  const [note,setNote]=useState('')
  const load=useCallback(async()=>{
    setLoading(true)
    try {
      const response=await api.get<AttentionResponse>('/attention',{params:{include_history:showHistory}})
      setData(response.data)
      setError(null)
    }catch(e){setError(humanError(e))}
    finally{setLoading(false)}
  },[showHistory])
  useEffect(()=>{void load()},[load])
  const visible=useMemo(()=>data?.items.filter(x=>
    (status==='ALL'||(status==='ACTIVE'?x.status!=='RESOLVED' && !x.superseded_by_id:x.status===status))&&
    (x.investor_id+' '+x.rule_id+' '+x.title).toLowerCase().includes(search.trim().toLowerCase()))||[],[data,status,search])
  useEffect(()=>{
    if(!visible.length){setSelected(null);return}
    if(!selected||!visible.some(x=>x.id===selected))setSelected(visible[0].id)
  },[visible,selected])
  const caseDetail=visible.find(x=>x.id===selected)||null
  function openAction(a:Action){setAction(a);setNote('');setError(null);setNotice(null)}
  async function apply(){
    if(!caseDetail||!action)return
    setSending(true);setError(null);setNotice(null)
    try{
      await api.post(`/attention/${caseDetail.id}/actions`,{action,note})
      setNotice(`${caseDetail.investor_id}: ${actionName[action]} recorded.`)
      setAction(null);setNote('')
      await load()
    }catch(e){setError(humanError(e))}
    finally{setSending(false)}
  }
  return <div className="page-fade advc-flow-page">
    <div className="standard-heading"><button className="advc-primary desk-heading-action" onClick={()=>setManual(!manual)}>{manual?'Close form':'+ Create a review'}</button>
      <h1>Attention Radar</h1>
      <p>Prioritized investor reviews.</p>
    </div>
    {manual&&<form className="panel-card desk-form" onSubmit={createReview}><h2>Start a client review</h2><p>A meeting or client request is enough to start. A detected pattern is optional.</p><label htmlFor="review-client">Client</label><select id="review-client" required value={clientId} onChange={e=>setClientId(e.target.value)}><option value="">Choose an assigned client</option>{clients.map(c=><option key={c.id} value={c.id}>{c.display_name} · {c.id}</option>)}</select><label>Review title<input required minLength={8} maxLength={180} value={manualTitle} onChange={e=>setManualTitle(e.target.value)} placeholder="Review the client’s upcoming liquidity needs"/></label><label>Why this review matters<textarea required minLength={12} maxLength={2000} value={manualReason} onChange={e=>setManualReason(e.target.value)}/></label><button className="advc-primary" disabled={sending}>Create client review</button></form>}
    {error&&<div className="error-banner" role="alert"><CircleAlert size={18}/>{error}</div>}
    {notice&&<div className="dt-notice" role="status"><CircleCheck size={18}/>{notice}</div>}
    <div className="advc-summary">
      <div className="advc-summary-card"><span>Open cases</span><strong>{data?.counts.OPEN??'—'}</strong></div>
      <div className="advc-summary-card"><span>In review</span><strong>{data?.counts.IN_REVIEW??'—'}</strong></div>
      <div className="advc-summary-card"><span>Need verification</span><strong>{data?.counts.NEEDS_DATA??'—'}</strong></div>
      <div className="advc-summary-card"><span>Resolved</span><strong>{data?.counts.RESOLVED??'—'}</strong></div>
    </div>
    <div className="advc-topbar panel-card">
      <div className="advc-search"><Search size={17}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search investor or review…" aria-label="Search cases"/></div>
      <div className="advc-filter"><Filter size={15}/><select aria-label="Filter case status" value={status} onChange={e=>setStatus(e.target.value)}>
        <option value="ACTIVE">Active cases</option><option value="ALL">All cases</option>
        <option value="OPEN">Open</option><option value="IN_REVIEW">In review</option>
        <option value="NEEDS_DATA">Need verification</option><option value="RESOLVED">Resolved</option>
      </select></div>
      <label style={{display:'flex',alignItems:'center',gap:6,fontSize:12}}><input type="checkbox" checked={showHistory} onChange={e=>setShowHistory(e.target.checked)} />Show case history</label>
      <button className="advc-quiet-btn" onClick={()=>void load()} disabled={loading}><RefreshCw size={16}/> Refresh</button>
    </div>
    <div className="advc-two-col concept-radar-layout">
      <div className="advc-case-list">
        {loading?<div className="panel-card advc-empty">Loading your review cases…</div>:visible.length===0?<div className="panel-card advc-empty"><ShieldCheck size={32}/><strong>No cases match this filter</strong><span>Run Pattern Explorer after importing data, or choose a different filter.</span><Link to="/patterns">Open Pattern Explorer <ArrowRight size={14}/></Link></div>:
          <div className="investor-table concept-radar-table"><table><thead><tr><th>Client</th><th>Attention reason</th><th>Priority</th><th>Action</th></tr></thead><tbody>{visible.map((c,i)=><tr className={selected===c.id?'concept-selected-row':''} key={c.id}><td><button className="concept-client-button advc-case-card" onClick={()=>{setSelected(c.id);setAction(null)}}><span className={`client-avatar avatar-${i%5}`}>{(c.investor_name||c.investor_id).split(' ').map(s=>s[0]).slice(0,2).join('')}</span><strong>{c.investor_name||c.investor_id}</strong></button></td><td><strong>{c.rule_id.startsWith('MANUAL_')?c.title:ruleName(c.rule_id)}</strong><small>{caseSummary(c.reason)}</small></td><td><span className={`overview-priority ${c.priority.toLowerCase()}`}>{priorityName(c.priority)}</span></td><td><button className="concept-view" aria-label={`View review for ${c.investor_name||c.investor_id}`} onClick={()=>{setSelected(c.id);setAction(null)}}>View</button></td></tr>)}</tbody></table></div>}
      </div>
      <div className="panel-card advc-detail">
        {!caseDetail?<div className="advc-empty"><Eye size={32}/><strong>Select a review case</strong><span>Choose an investor to see the underlying observation, action and source evidence.</span></div>:
          <><div className="advc-detail-kicker"><span>REVIEW DETAILS</span><span className={`advc-dot-status ${caseDetail.status.toLowerCase()}`}>{statusLabel[caseDetail.status]}</span></div>
          <h2>{caseDetail.investor_name||caseDetail.investor_id}</h2><p className="advc-lead">{ruleName(caseDetail.rule_id)}</p>
          {caseDetail.ranking&&<div className="desk-ranking"><div><span className="desk-eyebrow">WHY THIS REVIEW IS RANKED HERE</span><strong>{caseDetail.ranking.score}<small> review points</small></strong></div><div className="desk-ranking-factors"><span>{caseDetail.ranking.overdue_tasks} overdue tasks</span><span>{caseDetail.ranking.due_soon_tasks} due this week</span><span>{caseDetail.ranking.due_advice_reviews} advice reviews due</span></div><p>Evaluated {caseDetail.ranking.evaluated_on} · Source {caseDetail.ranking.source_age_days} days old{caseDetail.ranking.stale_source?' — request an updated record.':''}</p><details><summary>How the score is calculated</summary><dl>{Object.entries(caseDetail.ranking.components).map(([k,v])=><div key={k}><dt>{k.replaceAll('_',' ')}</dt><dd>{String(v)}</dd></div>)}<div><dt>obligation points</dt><dd>{caseDetail.ranking.obligation_points}</dd></div></dl><p>{caseDetail.ranking.explanation}</p></details></div>}
          <div className="advc-data-strip"><span>Source date <strong>{caseDetail.source_date}</strong></span><span>Evidence rows <strong>{caseDetail.evidence_source_row_ids.length}</strong></span><span>Priority <strong>{priorityName(caseDetail.priority)}</strong></span></div>
          <div className="advc-detail-section"><h3><TriangleAlert size={16}/> Why this appeared</h3><p>{caseReason(caseDetail.reason)}</p>
          {caseScore(caseDetail.reason)&&<div className="advc-score-details">
            {!caseDetail.ranking&&<span>Original review score <strong>{caseScore(caseDetail.reason)?.score}/95</strong></span>}
            {caseScore(caseDetail.reason)?.negativeMonths!=null&&<span>Negative-gap months <strong>{caseScore(caseDetail.reason)?.negativeMonths}/{caseScore(caseDetail.reason)?.observedMonths}</strong></span>}
            {caseScore(caseDetail.reason)?.gap&&<span>Sum of reported gaps <strong>{caseScore(caseDetail.reason)?.gap} pp</strong></span>}
          </div>}</div>
          <div className="advc-detail-section"><h3><ClipboardList size={16}/> Recommended review</h3><p>{caseDetail.suggested_action}</p></div>
          {caseDetail.resolution_note&&<div className="advc-resolution"><strong>Recorded resolution</strong><p>{caseDetail.resolution_note}</p></div>}
          <div className="advc-evidence-note"><ShieldCheck size={17}/>{caseReason(caseDetail.data_note)}</div>
          <div className="advc-actions"><Link className="advc-link-btn" to={`/investors?selected=${encodeURIComponent(caseDetail.investor_id)}`}>Investor 360° <ArrowRight size={15}/></Link>
            {user?.role==='ADVISOR'&&!caseDetail.superseded_by_id&&caseDetail.status!=='RESOLVED'&&<Link className="advc-primary" to={`/advice?alert=${encodeURIComponent(caseDetail.id)}`}>Draft advice <ArrowRight size={15}/></Link>}
          </div>
          {caseDetail.superseded_by_id&&<div className="advc-evidence-note"><ShieldCheck size={17}/>Historical review case. Open the current case from the active queue to take action.</div>}
          {user?.role==='ADVISOR'&&!caseDetail.superseded_by_id&&<div className="advc-review-actions">
            <div className="advc-section-small">REVIEW ACTIONS</div>
            {caseDetail.status==='OPEN'&&<button onClick={()=>openAction('START_REVIEW')}>Start review</button>}
            {['OPEN','IN_REVIEW'].includes(caseDetail.status)&&<button onClick={()=>openAction('REQUEST_DATA')}>Request data</button>}
            {caseDetail.status!=='RESOLVED'&&<button onClick={()=>openAction('RESOLVE')}>Resolve with note</button>}
            {caseDetail.status==='NEEDS_DATA'&&<button onClick={()=>openAction('START_REVIEW')}>Resume review</button>}
            {caseDetail.status==='RESOLVED'&&<button onClick={()=>openAction('REOPEN')}>Reopen case</button>}
          </div>}
          {user?.role==='SUPERVISOR'&&<div className="advc-evidence-note"><ShieldCheck size={17}/> Administrators can monitor cases; assigned advisors record review actions.</div>}
          {action&&<div className="advc-action-form"><strong>{actionName[action]}</strong><p>Actions and notes are saved in the audit history.</p>
            {action!=='START_REVIEW'&&<textarea rows={3} value={note} onChange={e=>setNote(e.target.value)} placeholder="Record the evidence or reason (at least 12 characters)"/>}
            <div className="advc-actions"><button className="advc-primary" disabled={sending||(action!=='START_REVIEW'&&note.trim().length<12)} onClick={()=>void apply()}>{sending?'Saving…':'Confirm action'}</button><button className="advc-quiet-btn" onClick={()=>setAction(null)}>Cancel</button></div>
          </div>}
          </>}
      </div>
    </div>
    <div className="concept-two-panels"><section className="panel-card concept-card"><h2>Attention distribution</h2><RingChart center={String(visible.length)} label="Cases in view" items={['P1','P2','P3','V_VERIFY'].map((key,i)=>({name:priorityName(key),value:visible.filter(c=>c.priority===key).length,color:['#ed7182','#ffbe49','#18b6a1','#7d8fd3'][i]}))}/></section><section className="panel-card concept-card"><h2>Review categories</h2><div className="concept-bar-list">{Array.from(new Set(visible.map(c=>c.rule_id))).map(key=>{const count=visible.filter(c=>c.rule_id===key).length;return <div key={key}><span>{ruleName(key)}</span><div><i style={{width:`${visible.length?count/visible.length*100:0}%`}}/></div><strong>{count}</strong></div>})}</div><p className="concept-footnote">Counts reflect the current status and search filters.</p></section></div>
  </div>
}

