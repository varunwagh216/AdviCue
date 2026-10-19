import ExploreWorkflows from '../components/ExploreWorkflows'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { compactINR, type BookSummary } from '../components/ConceptCharts'
import FinancialPanel from '../components/FinancialPanel'
import { ArrowLeft, ArrowRight, CircleAlert, FileSpreadsheet, Search, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, humanError, type Investor, type InvestorDetails } from '../lib/api'

export default function Investors() {
  const [investors,setInvestors] = useState<Investor[]>([])
  const [query,setQuery] = useState('')
  const [riskFilter,setRiskFilter]=useState('ALL')
  const [book,setBook]=useState<BookSummary|null>(null)
  useEffect(()=>{api.get<BookSummary>('/workspace-summary').then(r=>setBook(r.data)).catch(e=>setError(humanError(e)))},[])
  const [searchParams,setSearchParams]=useSearchParams()
  const selected=searchParams.get('selected')
  useEffect(()=>{setQuery(searchParams.get('q')||'')},[searchParams])
  const setSelected=(id:string|null)=>setSearchParams(id?{selected:id}:{})
  const [details,setDetails]=useState<InvestorDetails|null>(null)
  const [loading,setLoading] = useState(true)
  const [detailsLoading,setDetailsLoading]=useState(false)
  const [error,setError] = useState<string | null>(null)
  useEffect(()=>{
    let active=true
    api.get<{items:Investor[]}>('/investors')
      .then(res=>{if(active)setInvestors(res.data.items)})
      .catch(err=>{if(active)setError(humanError(err))})
      .finally(()=>{if(active)setLoading(false)})
    return ()=>{active=false}
  },[])
  useEffect(()=>{
    if(!selected){setDetails(null);return}
    let active=true
    setDetailsLoading(true);setError(null)
    api.get<InvestorDetails>(`/investors/${encodeURIComponent(selected)}`)
      .then(res=>{if(active)setDetails(res.data)})
      .catch(err=>{if(active)setError(humanError(err))})
      .finally(()=>{if(active)setDetailsLoading(false)})
    return ()=>{active=false}
  },[selected])
  const filtered=investors.filter(i=>`${i.display_name} ${i.id} ${i.primary_goal||''} ${i.source_advisor_code??''}`.toLowerCase().includes(query.toLowerCase()) && (riskFilter==='ALL'||i.risk_profile===riskFilter))
  const fmtAmount=(v:string|null)=>v===null?'Not available':`₹${Number(v).toLocaleString('en-IN',{maximumFractionDigits:2})}`
  return <div className="page-fade"><ExploreWorkflows area="clients"/>
    <div className="standard-heading"><h1>My clients</h1><p>One client workspace for holdings, goals, agreed advice and meeting knowledge.</p></div>
    {error&&<div className="error-banner" role="alert"><CircleAlert size={18}/>{error}</div>}
    {!selected&&<div className="overview-metrics concept-investor-metrics">{[{name:'Total clients',value:investors.length},{name:'Recorded holdings',value:book?compactINR(book.recorded_holdings_total):'—'},{name:'Average recorded holding',value:book&&investors.length?compactINR(String(Number(book.recorded_holdings_total)/investors.length)):'—'},{name:'Risk profiles',value:Object.keys(book?.risk_counts||{}).length}].map(m=><div className="overview-metric" key={m.name}><span>{m.name}</span><strong>{loading?'—':m.value}</strong></div>)}</div>}
    {selected?<>
      <button className="dt-back" onClick={()=>setSelected(null)}><ArrowLeft size={17}/> Back to investors</button>
      {detailsLoading?<div className="panel-card dt-placeholder">Loading source records…</div>:details&&<>
        <div className="dt-person-header panel-card"><div><div className="eyebrow">{details.investor.id}</div><h2>{details.investor.display_name}</h2><p>{details.investor.primary_goal||'Goal not recorded'} · {details.investor.city??'City unavailable'} · {details.investor.risk_profile??'Risk profile not available'} risk profile</p></div></div>
        <FinancialPanel key={selected} investorId={selected}/>
        <details className="panel-card focus-panel focus-disclosure"><summary>Instrument-level source holdings</summary>
          {details.holdings.length===0?<div className="dt-placeholder">No holding records available</div>:<div className="investor-table"><table><thead><tr><th>Instrument</th><th>Asset class</th><th>Recorded value</th><th>As-of date</th></tr></thead><tbody>{details.holdings.map(h=><tr key={h.source_row_id}><td><strong>{h.instrument_name}</strong></td><td>{h.asset_class}</td><td>{fmtAmount(h.current_value)}</td><td>{h.as_of_date}</td></tr>)}</tbody></table></div>}
        </details>

      </>}
    </>:<div className="panel-card"><div className="table-toolbar"><label className="concept-risk-filter">Profile<select aria-label="Filter investor risk profile" value={riskFilter} onChange={e=>setRiskFilter(e.target.value)}><option value="ALL">All profiles</option>{Object.keys(book?.risk_counts||{}).map(k=><option key={k}>{k}</option>)}</select></label><div className="table-count"><Users size={19}/> {loading?'Loading…':`${investors.length} clients`}</div><div className="table-search"><Search size={17}/><input aria-label="Search investors" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search clients or goals…" /></div></div>
      {filtered.length===0?<div className="empty-state"><div className="empty-art"><FileSpreadsheet size={39} strokeWidth={1.3}/></div><h3>{loading?'Loading investor records…':investors.length?'No matching investors':'No investor records assigned'}</h3><p>{investors.length?'Try another search.':'Use Data Management to import the sample workbook. Only your assigned investors will appear here.'}</p><Link to="/attention" className="outlined-action">Open Attention Radar <ArrowRight size={16}/></Link></div>:<div className="investor-table"><table><thead><tr><th>Client</th><th>Risk profile</th><th>Primary goal</th><th></th></tr></thead><tbody>{filtered.map(i=><tr key={i.id} className="dt-click-row" onClick={()=>setSelected(i.id)}><td><button className="concept-client-button" onClick={()=>setSelected(i.id)}><span className="client-avatar">{i.display_name.split(' ').map(s=>s[0]).slice(0,2).join('')}</span><strong>{i.display_name}</strong></button></td><td><span className={`concept-risk ${(i.risk_profile||'').toLowerCase()}`}>{i.risk_profile??'Not available'}</span></td><td>{i.primary_goal??'Not available'}</td><td><ArrowRight size={16}/></td></tr>)}</tbody></table></div>}
    </div>}

  </div>
}
