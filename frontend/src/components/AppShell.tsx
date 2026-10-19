import { useEffect,useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Home, Layers3, Bell, BrainCircuit, ClipboardCheck, Database, LogOut, Menu, Radar, Search, Users, X } from 'lucide-react'
import LocalStatus from './LocalStatus'
import Brand from './Brand'
import { useAuth } from '../context/AuthContext'

const navigation = [
  {label:'Home',path:'/',icon:Home},
  {label:'Reviews',path:'/attention',icon:Radar},
  {label:'Clients',path:'/investors',icon:Users},
  {label:'Pattern detection',path:'/patterns',icon:Layers3},
  {label:'Advice & follow-ups',path:'/advice',icon:ClipboardCheck},
  {label:'Meetings',path:'/local-ai',icon:BrainCircuit},
  {label:'Data tools',path:'/data-trust',icon:Database},
]

const titles:Record<string,string> = {
  '/':'Home','/investors':'Clients','/attention':'Reviews',
  '/patterns':'Pattern detection','/advice':'Advice & Follow-ups',
  '/local-ai':'Meetings','/data-trust':'Data tools',
  '/activity':'Activity History','/pilot':'Advisor pilot',
}
export default function AppShell(){
  const {user,logout}=useAuth()
  const [open,setOpen]=useState(false)
  const [globalQuery,setGlobalQuery]=useState('')
  const [signingOut,setSigningOut]=useState(false)
  const navigate=useNavigate()
  const location=useLocation()
  useEffect(()=>{window.scrollTo({top:0,behavior:'instant'})},[location.pathname])
  async function signOut(){
    setSigningOut(true)
    try{await logout()}catch{ /* local session cleared by auth context */ }
    finally{setSigningOut(false);navigate('/login')}
  }
  return <div className="app-layout advisor-layout">
    {open&&<button className="mobile-scrim" onClick={()=>setOpen(false)} aria-label="Close navigation"/>}
    <aside className={`sidebar ${open?'sidebar-open':''}`}>
      <div className="sidebar-brand"><Brand/><button className="close-mobile" aria-label="Close" onClick={()=>setOpen(false)}><X size={20}/></button></div>

      <div className="sidebar-section-caption">ADVISOR WORKSPACE</div>
      <nav className="side-nav" aria-label="Main navigation">
        {navigation.map(item=><NavLink onClick={()=>setOpen(false)} key={item.path} to={item.path} end={item.path==='/' }
          className={({isActive})=>`nav-item ${isActive?'active':''}`}>
          <item.icon size={19} strokeWidth={1.85}/><span>{item.label}</span>
        </NavLink>)}
      </nav>
      <div className="concept-sidebar-bottom"><LocalStatus/><div className="concept-sidebar-user"><span className="client-avatar">{(user?.name||'A').split(' ').map(s=>s[0]).slice(0,2).join('')}</span><div><strong>{user?.name}</strong><small>Financial advisor</small></div><button onClick={signOut} disabled={signingOut} aria-label="Sign out"><LogOut size={16}/></button></div></div>

    </aside>
    <a className="skip-link" href="#workspace-content">Skip to content</a><main className="main-wrap">
      <header className="topbar">
        <div className="topbar-left">
          <button className="mobile-menu" onClick={()=>setOpen(true)} aria-label="Open navigation"><Menu size={22}/></button>
          {location.pathname!=='/'&&<form className="concept-global-search" onSubmit={e=>{e.preventDefault();navigate(`/investors?q=${encodeURIComponent(globalQuery.trim())}`);setOpen(false)}}><Search size={15}/><input aria-label="Search clients" placeholder="Search clients, goals or IDs…" value={globalQuery} onChange={e=>setGlobalQuery(e.target.value)}/><kbd>Enter</kbd></form>}<span className="concept-page-context">{titles[location.pathname]||(location.pathname.startsWith('/advice/follow-ups')?'Follow-ups':location.pathname.startsWith('/advice/')?'Advice review':'Workspace')}</span>
        </div>
        <div className="topbar-right"><NavLink className="concept-bell" to="/attention" aria-label="Open client attention"><Bell size={18}/><i/></NavLink>
          <div className="profile-chip"><div className="avatar">{(user?.name||'A').slice(0,1).toUpperCase()}</div><div className="profile-info"><strong>{user?.name}</strong><small>Financial Advisor</small></div></div>
          <button className="logout-btn" title="Sign out" onClick={signOut} disabled={signingOut}><LogOut size={18}/></button>
        </div>
      </header>
      <div className="content-area" id="workspace-content"><Outlet/></div>
    </main>
  </div>
}
