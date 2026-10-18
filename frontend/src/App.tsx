import { Navigate, Route, Routes } from 'react-router-dom'
import { lazy, Suspense, type ReactNode } from 'react'
import { useAuth } from './context/AuthContext'
import Login from './pages/Login'
const Home=lazy(()=>import('./pages/Home'))
const FollowUps=lazy(()=>import('./pages/FollowUps'))
const AdviceDetail=lazy(()=>import('./pages/AdviceDetail'))
const Pilot=lazy(()=>import('./pages/Pilot'))
const ReviewDesk=lazy(()=>import('./pages/ReviewDesk'))
const Investors=lazy(()=>import('./pages/Investors'))
const DataTrust=lazy(()=>import('./pages/DataTrust'))
const PatternExplorer=lazy(()=>import('./pages/PatternExplorer'))
const AdviceLedger=lazy(()=>import('./pages/AdviceList'))
import AppShell from './components/AppShell'
const LocalAI=lazy(()=>import('./pages/LocalAI'))
const AuditTrail=lazy(()=>import('./pages/AuditTrail'))

function LegacyAccountNotice(){
  const {logout}=useAuth()
  return <div className="boot-screen"><div className="panel-card" style={{padding:32,maxWidth:460}}>
    <h2>Advisor Workspace</h2>
    <p>This workspace is for advisors. Sign in with your advisor account.</p>
    
    <button className="sign-in-button" onClick={()=>void logout()}>Sign out</button>
  </div></div>
}
function RequireAdvisor({children}:{children:ReactNode}) {
  const {user,checking}=useAuth()
  if(checking)return <div className="boot-screen"><div className="spinner"/><span>Preparing your workspace…</span></div>
  if(!user)return <Navigate to="/login" replace/>
  // This release is an advisor-facing workspace; inherited admin accounts are
  // preserved in SQLite for compatibility, not given an overlapping UI.
  if(user.role!=='ADVISOR')return <LegacyAccountNotice/>
  return children
}

export default function App(){
  return <Suspense fallback={<div className="boot-screen" role="status"><div className="spinner"/><span>Opening your workspace…</span></div>}><Routes>
    <Route path="/login" element={<Login/>}/>
    <Route element={<RequireAdvisor><AppShell/></RequireAdvisor>}>
      <Route index element={<Home/>}/>
      <Route path="investors" element={<Investors/>}/>
      <Route path="attention" element={<ReviewDesk/>}/>
      <Route path="advice" element={<AdviceLedger/>}/>
      <Route path="advice/follow-ups" element={<FollowUps/>}/>
      <Route path="advice/follow-ups/new" element={<FollowUps create/>}/>
      <Route path="advice/follow-ups/:taskId" element={<FollowUps/>}/>
      <Route path="advice/:recordId" element={<AdviceDetail/>}/>
      <Route path="pilot" element={<Pilot/>}/>
      <Route path="local-ai" element={<LocalAI/>}/>
      <Route path="data-trust" element={<DataTrust/>}/>
      <Route path="activity" element={<AuditTrail/>}/>
      <Route path="patterns" element={<PatternExplorer/>}/>
    </Route>
    <Route path="*" element={<Navigate to="/" replace/>}/>
  </Routes></Suspense>
}
