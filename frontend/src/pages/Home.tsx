import {recordText} from '../lib/display'
import { useEffect,useState,type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight,ArrowUp,Sparkles,Search } from 'lucide-react'
import { api,humanError } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import YourDay from '../components/YourDay'
import Welcome from '../components/Welcome'
import VoiceSearch from '../components/VoiceSearch'
type Summary={assigned_clients:number;clients_with_open_reviews:number;high_priority_clients:number;due_follow_ups:number;as_of:string}
type Result={mode:string;warning:string|null;answer:string;note:string;items:Array<{id:string;kind:string;client_name:string|null;title:string;detail:string;date:string|null;href:string}>}
export default function Home(){
 const [summary,setSummary]=useState<Summary|null>(null),[query,setQuery]=useState(''),[result,setResult]=useState<Result|null>(null),[busy,setBusy]=useState(false),[voiceBusy,setVoiceBusy]=useState(false),[error,setError]=useState('')
 useEffect(()=>{void api.get<Summary>('/home').then(r=>setSummary(r.data)).catch(e=>setError(humanError(e)))},[])
 async function search(text:string){if(text.trim().length<3||busy||voiceBusy)return;setQuery(text);setBusy(true);setError('');setResult(null);try{setResult((await api.post<Result>('/assistant/search',{query:text},{timeout:190000})).data)}catch(e){setError(humanError(e))}finally{setBusy(false)}}
 const {user}=useAuth()
 const hour=new Date().getHours();const greeting=hour<12?'Good morning':hour<18?'Good afternoon':'Good evening'
 return <div className="page-fade home-page"><Welcome/><section className="home-welcome"><span className="home-date">{new Date().toLocaleDateString('en-IN',{weekday:'long',day:'numeric',month:'long'})}</span><h1>{greeting}, {user?.name?.split(" ")[0]||"Advisor"}<span>.</span></h1><p>A clear view of your day.</p>
 <div className="home-counts" aria-label="Your client book"><Link to="/investors"><strong>{summary?.assigned_clients??'—'}</strong><span>Clients</span></Link><Link to="/attention"><strong>{summary?.clients_with_open_reviews??'—'}</strong><span>Open reviews</span></Link><Link to="/advice/follow-ups"><strong>{summary?.due_follow_ups??'—'}</strong><span>Follow-ups due</span></Link></div>
 <div className="home-assistant"><div className="home-suggestions" aria-label="Suggested questions">{["What’s for today?",'Which clients need my attention?','Reviews & follow-ups'].map(text=><button key={text} disabled={busy||voiceBusy} onClick={()=>void search(text)}>{text}<ArrowUpRight size={14}/></button>)}</div>
 <form className="home-search" onSubmit={(e:FormEvent)=>{e.preventDefault();void search(query)}}><Sparkles size={24}/><label className="sr-only" htmlFor="home-query">Ask AdviCue AI</label><input id="home-query" autoComplete="off" value={query} maxLength={1200} onChange={e=>setQuery(e.target.value)} placeholder="Ask about your clients, today’s reviews or follow-ups…"/><VoiceSearch disabled={busy} onActivity={setVoiceBusy} onTranscript={text=>{setQuery(text);setError('');document.getElementById('home-query')?.focus()}}/><button aria-label="Search with AdviCue AI" disabled={busy||voiceBusy||query.trim().length<3}><ArrowUp size={21}/></button></form><p className="home-search-note"><span className="home-local-dot"/> Private voice and text search · Processed on this computer</p></div></section>
 {error&&<p role="alert" className="error-banner">{error} <button onClick={()=>void search(query)}>Retry search</button></p>}{busy&&<div className="home-thinking" role="status"><Sparkles size={18}/> Searching your workspace…</div>}
 {!result&&!busy&&<YourDay/>}
 {result&&<section className="home-results" aria-live="polite"><div className="home-result-heading"><Search size={19}/><h2>{result.answer}</h2><span>{result.mode==='LOCAL_AI'?'Local AI':'Record search'}</span></div>{result.warning&&<p className="focus-warning">{result.warning}</p>}<div className="home-result-grid">{result.items.map(item=><Link className="home-result-card" to={item.href} key={item.kind+item.id}><div><span>{item.kind.replaceAll('_',' ')}</span>{item.date&&<time>{item.date}</time>}</div>{item.client_name&&<strong>{item.client_name}</strong>}<h3>{recordText(item.title)}</h3><p>{recordText(item.detail)}</p><span className="home-open">Open record <ArrowUpRight size={15}/></span></Link>)}</div>{!result.items.length&&<p className="focus-empty">No matching records. Try a client name or a more specific question.</p>}<details className="answer-evidence"><summary>Supporting evidence and scope</summary><p>{result.note}</p><Link to="/data-trust">Review source records</Link></details><div className="focus-actions"><Link className="advc-primary" to="/attention">Review clients</Link><Link className="advc-quiet-btn" to="/advice/follow-ups">Open follow-ups</Link></div></section>}
 </div>
}
