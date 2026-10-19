import DataConnections from '../components/DataConnections'
import { useCallback, useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import { AlertCircle, AlertTriangle, ArrowRight, CheckCircle2, ClipboardCheck, Database, FileSpreadsheet, FolderOpen, LockKeyhole, RefreshCw, ShieldCheck, UploadCloud } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, humanError, type ImportBatch, type ImportIssue } from '../lib/api'
import { statusName } from '../lib/display'

type Issues = {items: ImportIssue[]; total: number}
type Reconciliation = {status:string; holding_class_pairs:number; transaction_class_pairs:number;
 matched_investor_class_pairs:number;transaction_only_pairs:number;holding_only_pairs:number;
 excluded_duplicate_copies:number;quarantined_date_rows:number;unreliable_sip_unit_price_rows:number;
 matched_fund_names_within_paired_classes:number;unique_transaction_fund_names_within_paired_classes:number;note:string}
const orderedSheets = ['investors', 'holdings', 'transactions', 'performance_history']
const sheetLabels:Record<string,string> = { investors:'Investors', holdings:'Holdings',transactions:'Transactions',performance_history:'Performance snapshots' }

export default function DataTrust() {
  const [batches,setBatches] = useState<ImportBatch[]>([])
  const [reconciliation,setReconciliation]=useState<Reconciliation|null>(null)
  const [assetReturns,setAssetReturns]=useState<{observations:number;asset_classes:string[];months:number;note:string}|null>(null)
  const [returnCsv,setReturnCsv]=useState<File|null>(null)
  const [returnBusy,setReturnBusy]=useState(false)
  const [selected,setSelected] = useState<string | null>(null)
  const [issues,setIssues] = useState<Issues>({items:[],total:0})
  const [issueOffset,setIssueOffset] = useState(0)
  const [loading,setLoading] = useState(true)
  const [busy,setBusy] = useState<'upload'|'commit'|null>(null)
  const [error,setError] = useState<string|null>(null)
  const [notice,setNotice] = useState<string|null>(null)
  const [file,setFile] = useState<File|null>(null)
  const [confirmed,setConfirmed] = useState(false)
  const [canManage,setCanManage]=useState(false)
  const [capabilityLoading,setCapabilityLoading]=useState(true)
  useEffect(()=>{
    api.get<{can_manage_workbooks:boolean}>('/advisor-capabilities')
      .then(r=>setCanManage(r.data.can_manage_workbooks))
      .catch(()=>setCanManage(false))
      .finally(()=>setCapabilityLoading(false))
  },[])
  const supervisor = canManage
  const active = batches.find(b=>b.id===selected)

  const refresh = useCallback(async () => {
    if (!supervisor) {setLoading(false);return}
    const res=await api.get<{items:ImportBatch[]}>('/imports')
    setBatches(res.data.items)
    try { const returns=await api.get<{observations:number;asset_classes:string[];months:number;note:string}>('/imports/asset-returns/summary');setAssetReturns(returns.data) }
    catch {setAssetReturns(null)}
    try { const reconciled=await api.get<Reconciliation>('/imports/reconciliation/summary');setReconciliation(reconciled.data) }
    catch { setReconciliation(null) }
    setSelected(prev=>prev && res.data.items.some(b=>b.id===prev) ? prev : res.data.items[0]?.id??null)
    setLoading(false)
  },[supervisor])
  useEffect(()=>{refresh().catch(e=>{setError(humanError(e));setLoading(false)})},[refresh])
  useEffect(()=>{
    if (!selected) {setIssues({items:[],total:0});return}
    let cancelled=false
    api.get<Issues>(`/imports/${selected}/issues`,{params:{limit:50,offset:issueOffset}})
      .then(r=>{if(!cancelled)setIssues(r.data)})
      .catch(e=>{if(!cancelled)setError(humanError(e))})
    return ()=>{cancelled=true}
  },[selected,issueOffset])

  async function upload(e:FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!file) {setError('Choose the investor .xlsx workbook first.');return}
    setError(null);setNotice(null);setBusy('upload');setConfirmed(false)
    try {
      const form=new FormData()
      form.append('file',file)
      const res=await api.post<ImportBatch>('/imports',form,{headers:{'Content-Type':undefined},timeout:90000})
      await refresh()
      setSelected(res.data.id);setIssueOffset(0);setFile(null)
      const input=document.getElementById('workbook-input') as HTMLInputElement|null
      if(input)input.value=''
      setNotice(res.data.error_count ? 'Workbook staged with blocking errors. Review the issues below.' : 'Workbook staged. Review the source counts and warnings before committing.')
    } catch(e){
      const message=humanError(e)
      const existing=/Workbook already uploaded in batch ([a-f0-9-]+)/i.exec(message)
      if(existing){
        await refresh()
        setSelected(existing[1]);setIssueOffset(0)
        setNotice('This workbook is already in Import History. Its existing validation report is selected below; uploading it again is unnecessary.')
        setError(null)
      }else setError(message)
    }
    finally{setBusy(null)}
  }

  async function commit() {
    if(!active || !confirmed)return
    setError(null);setNotice(null);setBusy('commit')
    try {
      const committed=await api.post(`/imports/${active.id}/commit`)
      setConfirmed(false)
      await refresh()
      setNotice(`Import saved. ${committed.data.existing_clients_retained??0} existing clients retained; ${committed.data.unchanged_observations_skipped??0} unchanged observations skipped. New dated evidence is ready for review.`)
    } catch(e){setError(humanError(e))}
    finally{setBusy(null)}
  }

  async function uploadReturnSeries(e:FormEvent<HTMLFormElement>){
    e.preventDefault();if(!returnCsv)return
    setReturnBusy(true);setError(null);setNotice(null)
    try{
      const data=new FormData();data.append('file',returnCsv)
      const res=await api.post<{imported:number}>('/imports/asset-returns/upload',data,{headers:{'Content-Type':undefined},timeout:90000})
      setReturnCsv(null)
      const control=document.getElementById('asset-return-csv') as HTMLInputElement|null
      if(control)control.value=''
      await refresh()
      setNotice(`${res.data.imported} source-labeled asset-class returns imported for optional descriptive proxy calculations.`)
    }catch(e){setError(humanError(e))}
    finally{setReturnBusy(false)}
  }

  if(capabilityLoading)return <div className="panel-card dt-placeholder">Checking local data-management permission…</div>
  if(!supervisor)return <div className="page-fade"><div className="standard-heading"><h1>Data management</h1><p>Keep client holdings current and export follow-ups to the tools you already use.</p></div><DataConnections/><div className="panel-card v6-record"><LockKeyhole size={24}/><p>You can update holdings for your assigned clients here. Full-book Excel imports require the authorized data operator.</p></div></div>

  return <div className="page-fade"><div className="standard-heading"><h1>Data management</h1><p>Upload holdings, check the preview, then save reviewed records to update your client views.</p><div className="focus-support-links"><Link to="/activity">Activity history</Link><a href="/examples/validation-guide.txt" download>Validation guide</a></div></div>
    <DataConnections/>
    <details className="panel-card v6-record"><summary>Excel imports and validation history</summary>
    <div className="dt-grid">
      <div className="panel-card dt-upload"><div className="dt-card-top"><div className="dt-card-icon"><UploadCloud size={22}/></div><div><h3>Upload workbook</h3><p>Four sheets · .xlsx · Maximum 10 MB</p></div></div>
        <form onSubmit={upload} className="dt-upload-form">
          <label className="dt-file-picker" htmlFor="workbook-input" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();const picked=e.dataTransfer.files[0];if(picked&&!picked.name.toLowerCase().endsWith('.xlsx')){setError('Choose an .xlsx workbook');return}if(picked){setFile(picked);setError(null)}}}><FileSpreadsheet size={27}/><strong>{file?.name || 'Choose the investor workbook'}</strong><span>Investors · Holdings · Transactions · Performance</span></label>
          <input id="workbook-input" type="file" accept=".xlsx" onChange={(e:ChangeEvent<HTMLInputElement>)=>{setFile(e.target.files?.[0]??null);setError(null)}} />
          <button className="dt-primary" type="submit" disabled={!file||busy!==null}>{busy==='upload'?'Validating workbook…':'Upload and validate'} <ArrowRight size={17}/></button>
        </form>
        <div className="dt-upload-note"><ShieldCheck size={16}/><span>Nothing is added to investor tables until you confirm the commit.</span></div>
      </div>
      <div className="panel-card dt-guidance"><div className="dt-card-top"><div className="dt-card-icon teal"><ClipboardCheck size={22}/></div><div><h3>Quality controls</h3><p>Built into each import</p></div></div>
        {['Required IDs, dates, and numeric formats','Broken investor references and duplicate candidates','Units × price valuation review warnings','Source rows and financial evidence preserved'].map(item=><div key={item} className="dt-guidance-line"><CheckCircle2 size={17}/><span>{item}</span></div>)}
        <p className="dt-subnote">Snapshot return percentages are stored as <b>source-reported</b>, not verified investment returns.</p>
      </div>
    </div>
    {error && <div className="error-banner" role="alert"><AlertCircle size={18}/>{error}</div>}
    {notice && <div className="dt-notice"><CheckCircle2 size={18}/>{notice}</div>}
    <div className="dt-section-head"><div><h2>Import history</h2><p>Select a batch to inspect its validation report.</p></div><button className="dt-reload" onClick={()=>refresh()} title="Refresh import history"><RefreshCw size={16}/> Refresh</button></div>
    <div className="dt-history-layout">
      <div className="panel-card dt-history-list">{loading?<div className="dt-placeholder">Loading imports…</div>:batches.length===0?<div className="dt-placeholder"><FolderOpen size={33}/><strong>No uploads yet</strong><span>Select the Excel workbook above to begin.</span></div>:batches.map(b=><button key={b.id} onClick={()=>{setSelected(b.id);setIssueOffset(0);setConfirmed(false)}} className={`dt-batch ${selected===b.id?'selected':''}`}><FileSpreadsheet size={20}/><div><strong>{b.filename}</strong><small>{new Date(b.created_at).toLocaleString('en-IN')} · {b.total_rows.toLocaleString('en-IN')} rows</small></div><span className={`dt-status ${b.status.toLowerCase()}`}>{statusName(b.status)}</span></button>)}</div>
      <div className="panel-card dt-report">
      {active ? <><div className="dt-report-head"><div><h3>Validation report</h3><span>Batch {active.id.slice(0,8)} · {active.status}</span></div><span className={`dt-status ${active.status.toLowerCase()}`}>{statusName(active.status)}</span></div>
        <div className="dt-counts"><div><strong>{active.total_rows.toLocaleString('en-IN')}</strong><span>Source rows</span></div><div><strong>{active.error_count}</strong><span>Blocking errors</span></div><div><strong>{active.warning_count}</strong><span>Warnings</span></div></div>
        <div className="dt-sheet-grid">{orderedSheets.map(s=><div key={s}><strong>{active.sheet_counts[s]??0}</strong><span>{sheetLabels[s]}</span></div>)}</div>
        <div className="dt-issues-heading"><h4>Quality findings <span>({issues.total})</span></h4>{issues.total===0&&<span className="dt-clean"><CheckCircle2 size={16}/> No issues detected</span>}</div>
        {issues.items.length>0&&<div className="dt-issues-scroll"><table className="dt-issues-table"><thead><tr><th>Severity</th><th>Location</th><th>Finding</th></tr></thead><tbody>{issues.items.map(x=><tr key={x.id}><td><span className={`dt-severity ${x.severity.toLowerCase()}`}>{x.severity}</span></td><td>{x.sheet_name} · Row {x.row_number}</td><td><strong>{statusName(x.code)}</strong><small>{x.message}</small></td></tr>)}</tbody></table></div>}
        {issues.total>50&&<div className="dt-pagination"><button disabled={issueOffset===0} onClick={()=>setIssueOffset(Math.max(0,issueOffset-50))}>Previous</button><span>{issueOffset+1}–{Math.min(issueOffset+50,issues.total)} of {issues.total}</span><button disabled={issueOffset+50>=issues.total} onClick={()=>setIssueOffset(issueOffset+50)}>Next</button></div>}
        {active.status==='STAGED' && <div className="dt-commit"><label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/><span>I have reviewed the source counts and any warnings. I understand no verified portfolio returns are calculated here.</span></label><button className="dt-primary" onClick={commit} disabled={!confirmed||busy!==null}>{busy==='commit'?'Committing…':'Commit accepted records'} <ArrowRight size={16}/></button></div>}
        {active.status==='BLOCKED'&&<div className="dt-blocked"><AlertTriangle size={18}/> This batch contains blocking errors. Correct the source workbook and upload a revised file; nothing has been added to normalized tables.</div>}
        {active.status==='COMMITTED'&&<div className="dt-committed"><CheckCircle2 size={19}/> Workbook successfully committed. <Link to="/investors">Browse investors <ArrowRight size={15}/></Link></div>}
      </>:<div className="dt-placeholder"><Database size={32}/><strong>No import selected</strong><span>Validated records will appear here after upload.</span></div>}
      </div>
    </div>
    
    <details className="panel-card concept-data-evidence"><summary>Source reconciliation & optional return evidence</summary>    {reconciliation&&<section className="panel-card" style={{padding:20,marginBottom:18}}>
      <h3><ShieldCheck size={18} style={{display:'inline',marginRight:8}}/>Cross-sheet reconciliation</h3>
      
      <div style={{display:'flex',gap:16,flexWrap:'wrap',marginTop:12,marginBottom:12}}>
        <span><strong>{reconciliation.matched_investor_class_pairs}</strong> matched investor/class pairs</span>
        <span><strong>{reconciliation.transaction_only_pairs}</strong> transaction-only pairs</span>
        <span><strong>{reconciliation.holding_only_pairs}</strong> holdings-only pairs</span>
        <span><strong>{reconciliation.excluded_duplicate_copies}</strong> duplicate copies excluded</span>
        <span><strong>{reconciliation.quarantined_date_rows}</strong> dates requiring verification</span>
        <span><strong>{reconciliation.unreliable_sip_unit_price_rows}</strong> unreliable SIP unit/price rows</span>
      </div>
      
    </section>}
    <section className="panel-card" style={{padding:20,marginBottom:18}}>
      <h3>Optional source-labeled asset-class returns</h3>
      <p>Optional source-return data for scenario comparisons. Verified attribution requires reviewed financial evidence.</p>
      <p>{assetReturns ? `${assetReturns.observations} observations · ${assetReturns.months} months · ${assetReturns.asset_classes.length} asset classes` : 'No sourced class-return series loaded.'}</p>
      <form onSubmit={uploadReturnSeries} style={{display:'flex',flexWrap:'wrap',alignItems:'center',gap:12,marginTop:12}}>
        <input id="asset-return-csv" type="file" accept=".csv,text/csv" aria-label="Choose sourced asset class returns CSV" onChange={e=>setReturnCsv(e.target.files?.[0]??null)}/>
        <button className="dt-primary" type="submit" disabled={!returnCsv||returnBusy}>{returnBusy?'Importing…':'Import sourced return CSV'}</button>
      </form>
      <small>CSV columns: month, asset_class, return_pct, source_reference.</small>
    </section>
</details>
  </details></div>
}
