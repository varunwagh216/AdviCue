import AskAdviCue from '../components/AskAdviCue'
import {recordText} from '../lib/display'
import { useEffect, useState } from 'react'
import { Link,useSearchParams } from 'react-router-dom'
import { BrainCircuit, CircleAlert, CircleCheck, FileAudio, FileText, LockKeyhole, Mic, Send, ShieldCheck } from 'lucide-react'
import { api, humanError, type Investor } from '../lib/api'
import { useAuth } from '../context/AuthContext'

type Brief = { id:string; investor_id:string; summary:string; cited_fact_ids:string[]; review_questions:string[]; model:string; created_at?:string }
type Note = { id:string; investor_id:string; status:'DRAFT'|'APPROVED'; input_method:'TEXT'|'LOCAL_AUDIO'; transcript:string; extracted_draft?:{coverage?:{characters_processed:number;total_characters:number;chunks:number;complete:boolean};summary:string;commitments:string[];review_questions:string[];preferences?:Record<string,string>}|null; approved_summary:string|null; approved_commitments:string[]|null;approved_preferences?:Record<string,string>|null; created_at:string; recording_consent:boolean }
type AIStatus = { runtime_state?:string; llama_cpp_local_config_valid:boolean; model:string; transcription_model:string; note:string }

export default function LocalAI() {
  const { user } = useAuth()
  const [routeParams]=useSearchParams()
  const [view,setView]=useState(routeParams.get('client')?'NOTES':'ASK')
  const [investors,setInvestors] = useState<Investor[]>([])
  const [selected,setSelected] = useState(routeParams.get('client')||'')
  const [brief,setBrief] = useState<Brief|null>(null)
  const [briefs,setBriefs] = useState<Brief[]>([])
  const [notes,setNotes] = useState<Note[]>([])
  const [configuration,setConfiguration] = useState<AIStatus|null>(null)
  const [transcript,setTranscript] = useState('')
  const [recording,setRecording] = useState<File|null>(null)
  const [consent,setConsent] = useState(false)
  const [reviewId,setReviewId] = useState('')
  const [reviewSummary,setReviewSummary] = useState('')
  const [commitments,setCommitments] = useState('')
  const [liquidity,setLiquidity] = useState('')
  const [riskConcerns,setRiskConcerns] = useState('')
  const [lifeEvents,setLifeEvents] = useState('')
  const [checkMetric,setCheckMetric] = useState<'equity_pct'|'fixed_deposit_pct'>('equity_pct')
  const [checkComparator,setCheckComparator] = useState<'>='|'<='>('>=')
  const [checkTarget,setCheckTarget] = useState('20')
  const [checkDue,setCheckDue] = useState('')
  const [checkStatuses,setCheckStatuses] = useState<Array<{id:string;metric:string;target_pct:string;status:string;due_date:string;observed_pct:string|null;illustrative_demo_only?:boolean}>>([])
  const [busy,setBusy] = useState('')
  const [error,setError] = useState('')
  const [notice,setNotice] = useState('')
  const [taskDates,setTaskDates]=useState<Record<string,string>>({})
  async function commitmentTask(note:Note,index:number){await run('task',async()=>{const key=note.id+index;if(!taskDates[key])throw new Error('Choose a follow-up date first');await api.post('/tasks',{source_meeting_id:note.id,commitment_index:index,title:note.approved_commitments![index],due_date:taskDates[key]});setNotice('Follow-up created from the approved commitment. Find it in Advice & Follow-ups.')})}

  useEffect(()=>{
    api.get<{items:Investor[]}>('/investors').then(r=>{setInvestors(r.data.items);if(r.data.items.length)setSelected(v=>v||r.data.items[0].id)}).catch(e=>setError(humanError(e)))
    api.get<AIStatus>('/ai/status').then(r=>setConfiguration(r.data)).catch(()=>{})
  },[])
  useEffect(()=>{
    setTranscript('');setRecording(null);setConsent(false);
    if(!selected){setBriefs([]);setNotes([]);setBrief(null);return}
    let active=true
    Promise.all([api.get<{items:Brief[]}>(`/ai/briefs/${encodeURIComponent(selected)}`),api.get<{items:Note[]}>('/meetings',{params:{investor_id:selected}})])
      .then(([b,n])=>{if(active){setBriefs(b.data.items);setNotes(n.data.items);setBrief(null);setReviewId('')}})
      .catch(e=>{if(active)setError(humanError(e))})
    return ()=>{active=false}
  },[selected])
  async function run(action:string, work:()=>Promise<void>){setBusy(action);setError('');setNotice('');try{await work()}catch(e){setError(humanError(e))}finally{setBusy('')}}
  async function reload(){
    const [b,n] = await Promise.all([api.get<{items:Brief[]}>(`/ai/briefs/${encodeURIComponent(selected)}`),api.get<{items:Note[]}>('/meetings',{params:{investor_id:selected}})])
    setBriefs(b.data.items);setNotes(n.data.items);await loadChecks()
  }
  async function generateBrief(){await run('brief', async()=>{
    const response=await api.post<Brief>('/ai/briefs',{investor_id:selected},{timeout:240000})
    setBrief(response.data);await reload();setNotice('New brief generated from sourced facts. Review the cited evidence before relying on it.')
  })}
  async function saveTypedNote(){await run('save', async()=>{
    await api.post('/meetings/notes',{investor_id:selected,transcript})
    setTranscript('');await reload();setNotice('Meeting note saved as a draft. It has not been approved.')
  })}
  async function transcribe(){await run('transcribe',async()=>{
    if(!recording)throw new Error('Select a recording first')
    const data=new FormData();data.append('investor_id',selected);data.append('recording_consent',String(consent));data.append('audio',recording)
    await api.post('/meetings/transcribe',data,{headers:{'Content-Type':undefined},timeout:240000})
    setRecording(null);setConsent(false);await reload();setNotice('Local transcription saved as a draft. Raw audio was not retained.')
  })}
  async function extract(note:Note){await run('extract-'+note.id,async()=>{
    const response=await api.post<Note>(`/meetings/${note.id}/extract`,{}, {timeout:1200000})
    const generated=response.data.extracted_draft
    setReviewId(note.id);setReviewSummary(generated?.summary??'');setCommitments((generated?.commitments??[]).join('\n'))
    setLiquidity(generated?.preferences?.liquidity_needs??'');setRiskConcerns(generated?.preferences?.risk_concerns??'');setLifeEvents(generated?.preferences?.life_events??'')
    await reload();setNotice('AI extraction is only a draft. Edit the summary and commitments, then approve explicitly.')
  })}
  function review(note:Note){setReviewId(note.id);setReviewSummary(note.extracted_draft?.summary??'');setCommitments((note.extracted_draft?.commitments??[]).join('\n'));
    setLiquidity(note.extracted_draft?.preferences?.liquidity_needs??'');setRiskConcerns(note.extracted_draft?.preferences?.risk_concerns??'');setLifeEvents(note.extracted_draft?.preferences?.life_events??'')}
  async function createCheck(note:Note){await run('check',async()=>{
    if(!checkDue)throw new Error('Choose a due date')
    await api.post(`/meetings/${note.id}/commitment-checks`,{metric:checkMetric,comparator:checkComparator,target_pct:Number(checkTarget),due_date:checkDue})
    setNotice('Measurable commitment check created. No outcome is assumed until later holdings are available.')
    await loadChecks()
  })}
  async function loadChecks(){if(!selected)return;const response=await api.get(`/investors/${encodeURIComponent(selected)}/commitment-checks`);setCheckStatuses(response.data.items)}
  async function discard(note:Note){if(!window.confirm('Delete this unapproved meeting draft and transcript?'))return;await run('discard',async()=>{await api.post(`/meetings/${note.id}/discard`);await reload();setReviewId('');setNotice('Draft discarded; content-free audit record retained.')})}
  async function approve(){await run('approve',async()=>{
    await api.post(`/meetings/${reviewId}/approve`,{summary:reviewSummary,commitments:commitments.split('\n').map(x=>x.trim()).filter(Boolean),
      preferences:Object.fromEntries(Object.entries({liquidity_needs:liquidity,risk_concerns:riskConcerns,life_events:lifeEvents}).filter(([,v])=>v.trim()).map(([k,v])=>[k,v.trim()]))})
    await reload();setReviewId('');setNotice('Meeting notes approved and audit event recorded. No advice or tasks were created automatically.')
  })}

  return <div className="page-fade advc-ai-page">
    <div className="standard-heading"><h1>Ask AdviCue</h1>
      <p>Answers, client briefs and meeting knowledge in one workspace.</p></div>
    {error&&<div className="error-banner" role="alert"><CircleAlert size={18}/>{error}</div>}
    {notice&&<div className="dt-notice" role="status"><CircleCheck size={18}/>{notice}</div>}
    <div className="ai-view-tabs" role="tablist" aria-label="AI workspace views">{[['ASK','Ask AI'],['BRIEFS','Client briefs'],['NOTES','Meetings']].map(([key,label])=><button key={key} role="tab" aria-selected={view===key} onClick={()=>setView(key)}>{label}</button>)}</div><div className="advc-ai-toolbar panel-card"><label htmlFor="ai-investor">Client</label><select id="ai-investor" disabled={!!busy} value={selected} onChange={e=>setSelected(e.target.value)}>
      {investors.length===0?<option value="">Import investors first</option>:investors.map(x=><option value={x.id} key={x.id}>{x.display_name}</option>)}
    </select><span><LockKeyhole size={15}/> {configuration?.runtime_state==='READY'?'Ready':configuration?.runtime_state==='STARTING'?'Starting':'Needs setup'}</span></div>
    {view==='ASK'&&<AskAdviCue clientName={investors.find(i=>i.id===selected)?.display_name||''}/>}<div className="advc-ai-grid">
      {view==='BRIEFS'&&<section className="panel-card advc-ai-section"><div className="advc-ai-section-title"><BrainCircuit size={20}/><div><h2>Client brief</h2></div></div>
        <p className="brief-intro">Prepare for your next conversation with {investors.find(i=>i.id===selected)?.display_name||'this client'}.</p><div className="ai-example-actions"><Link to={'/investors?selected='+selected}>Review portfolio</Link><button onClick={()=>setView('ASK')}>Ask a question ↗</button></div><button className="advc-primary" disabled={!selected||!!busy} onClick={generateBrief}><Send size={16}/>{busy==='brief'?'Generating…':'Generate grounded brief'}</button>
        
        {(brief||briefs[0])&&<div className="advc-ai-result"><h3>Latest client brief</h3><p>{recordText((brief??briefs[0]).summary)}</p>
          <h4>Questions for the advisor</h4><ul>{(brief??briefs[0]).review_questions.map((q,i)=><li key={i}>{q}</li>)}</ul>
          <span><ShieldCheck size={14}/> {(brief??briefs[0]).cited_fact_ids.length} source references · {(brief??briefs[0]).model}</span></div>}
        {!brief&&briefs.length===0&&<div className="advc-ai-placeholder"><FileText size={27}/><span>No brief generated for this investor yet.</span></div>}
      </section>}
      {view==='NOTES'&&<section className="panel-card advc-ai-section"><div className="advc-ai-section-title"><Mic size={20}/><div><h2>Capture a conversation</h2></div></div>
        {user?.role==='ADVISOR'?<><div className="ai-example-actions"><button onClick={()=>setTranscript(`Agenda for ${investors.find(i=>i.id===selected)?.display_name||'this client'}: review progress towards ${investors.find(i=>i.id===selected)?.primary_goal||'the agreed goal'}, confirm liquidity needs, and agree the next review date.`)}>Use client meeting agenda ↗</button><Link to={'/investors?selected='+selected}>Open client context</Link></div><label className="advc-ai-field">Typed meeting notes<textarea id="meeting-transcript" rows={5} value={transcript} onChange={e=>setTranscript(e.target.value)} placeholder="Type what was discussed, without inventing previous recommendations…"/></label>
          <button className="advc-primary" disabled={!selected||!!busy||transcript.trim().length<12} onClick={saveTypedNote}><FileText size={16}/> Save draft notes</button>
          <div className="advc-ai-upload"><strong><FileAudio size={17}/> Optional local transcription</strong><input type="file" aria-label="Meeting audio" accept=".wav,.mp3,.m4a,.ogg,.webm" onChange={e=>setRecording(e.target.files?.[0]??null)}/>
            <label className="advc-ai-consent"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>I confirm recording consent was obtained.</label>
            <button className="advc-quiet-btn" disabled={!recording||!consent||!!busy} onClick={transcribe}>{busy==='transcribe'?'Transcribing locally…':'Transcribe and create draft'}</button>
            <small>Offline whisper.cpp transcription. Install its local model first. WAV is supported directly; other formats require local FFmpeg. Raw audio is deleted after transcription.</small></div></>:<p className="advc-ai-hint">Meeting-note access is limited to authorized client records.</p>}
      </section>}
    </div>
    {view==='NOTES'&&<section className="panel-card advc-ai-section advc-ai-notes"><div className="advc-ai-section-title"><FileText size={20}/><div><h2>Drafts &amp; Approved Meeting Notes</h2></div></div>
      <div className="advc-ai-note-list">{notes.length===0?<p className="advc-ai-hint">No meeting notes for the selected investor.</p>:notes.map(note=><div className="advc-ai-note" key={note.id}>
        <div className="advc-ai-note-head"><strong>{note.input_method==='TEXT'?'Typed notes':'Local transcription'}</strong><span className={`advc-status-tag ${note.status.toLowerCase()}`}>{note.status}</span><small>{new Date(note.created_at).toLocaleDateString('en-IN')}</small></div>
        <details className="meeting-transcript"><summary>Read meeting transcript</summary><p>{recordText(note.transcript)}</p></details>
        {note.extracted_draft&&note.status==='DRAFT'&&<div className="advc-ai-extraction"><strong>Unapproved AI draft:</strong> {note.extracted_draft.summary}{note.extracted_draft.coverage&&<small className="desk-coverage">Complete transcript processed · {note.extracted_draft.coverage.characters_processed.toLocaleString()} characters · {note.extracted_draft.coverage.chunks} sections</small>}</div>}
        {note.status==='APPROVED'&&<div className="advc-ai-extraction"><strong>Advisor-approved summary:</strong> {recordText(note.approved_summary)}
          {!!Object.keys(note.approved_preferences??{}).length&&<p><strong>Approved client context:</strong> {Object.entries(note.approved_preferences??{}).map(([k,v])=>`${k.replaceAll('_',' ')}: ${v}`).join(' · ')}</p>}{!!note.approved_commitments?.length&&<ul>{note.approved_commitments.map((x,i)=><li className="desk-commitment-task" key={i}><span>{recordText(x)}</span><label>Follow-up date<input type="date" value={taskDates[note.id+i]||''} onChange={e=>setTaskDates({...taskDates,[note.id+i]:e.target.value})}/></label><button className="advc-quiet-btn" disabled={!!busy||!taskDates[note.id+i]} onClick={()=>void commitmentTask(note,i)}>Create task</button></li>)}</ul>}
          {user?.role==='ADVISOR'&&!!note.approved_commitments?.length&&<div className="advc-ai-review"><strong>Create a measurable commitment check</strong>
            <p>Only use targets actually documented in the approved meeting note. The system does not automatically interpret free-text promises.</p>
            <label>Metric<select value={checkMetric} onChange={e=>setCheckMetric(e.target.value as 'equity_pct'|'fixed_deposit_pct')}><option value="equity_pct">Equity %</option><option value="fixed_deposit_pct">Fixed deposit %</option></select></label>
            <label>Condition<select value={checkComparator} onChange={e=>setCheckComparator(e.target.value as '>='|'<=' )}><option value=">=">At least</option><option value="<=">At most</option></select></label>
            <label>Target %<input type="number" min="0" max="100" value={checkTarget} onChange={e=>setCheckTarget(e.target.value)}/></label>
            <label>Due date<input type="date" value={checkDue} onChange={e=>setCheckDue(e.target.value)}/></label>
            <button className="advc-quiet-btn" disabled={!!busy||!checkDue} onClick={()=>void createCheck(note)}>Create check</button>
          </div>}
          {user?.role==='ADVISOR'&&<p><Link to={`/advice?meeting_note=${encodeURIComponent(note.id)}`} className="advc-link-btn">Use as evidence in new advice draft</Link></p>}</div>}
        {user?.role==='ADVISOR'&&note.status==='DRAFT'&&<div className="advc-actions"><button disabled={!!busy} className="advc-quiet-btn" onClick={()=>void extract(note)}><BrainCircuit size={15}/> {busy==='extract-'+note.id?'Extracting…':'AI extract draft'}</button><button className="advc-quiet-btn" disabled={!!busy} onClick={()=>review(note)}>Review &amp; approve manually</button><button className="advc-quiet-btn" disabled={!!busy} onClick={()=>void discard(note)}>Discard draft</button></div>}
        {reviewId===note.id&&<div className="advc-ai-review"><label>Advisor-reviewed summary<textarea rows={3} value={reviewSummary} onChange={e=>setReviewSummary(e.target.value)}/></label><label>Commitments (one per line, only if documented)<textarea rows={3} value={commitments} onChange={e=>setCommitments(e.target.value)}/></label>
          <label>Liquidity needs (optional, advisor-approved)<textarea maxLength={300} rows={2} value={liquidity} onChange={e=>setLiquidity(e.target.value)}/></label>
          <label>Risk concerns (optional)<textarea maxLength={300} rows={2} value={riskConcerns} onChange={e=>setRiskConcerns(e.target.value)}/></label>
          <label>Life events (optional)<textarea maxLength={300} rows={2} value={lifeEvents} onChange={e=>setLifeEvents(e.target.value)}/></label>
          <div className="advc-actions"><button className="advc-primary" disabled={!!busy||reviewSummary.trim().length<12} onClick={approve}>Approve notes</button><button className="advc-quiet-btn" onClick={()=>setReviewId('')}>Cancel</button></div></div>}
      </div>)}</div>
    </section>}
    {view==='NOTES'&&!!checkStatuses.length&&<section className="panel-card advc-ai-section"><h2>Commitment verification</h2><p>Evaluated only against holdings dated after meeting approval. Checks without dated evidence remain unverified.</p>
      {checkStatuses.map(c=><p key={c.id}>{c.metric.replaceAll('_',' ')} {c.target_pct}% by {c.due_date}: <strong>{c.status.replaceAll('_',' ').toLowerCase()}</strong> {c.observed_pct!==null?`(observed ${c.observed_pct}%)`:''}</p>)}
      <button className="advc-quiet-btn" onClick={()=>void loadChecks()}>Refresh checks</button>
    </section>}
    <p className="page-footnote ai-workspace-footnote"><ShieldCheck size={16}/> All investor records are permission-scoped. AI assistance is optional and cannot approve advice, execute trades or invent verified returns.</p>
  </div>
}
