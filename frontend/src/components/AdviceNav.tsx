import { NavLink,useLocation } from 'react-router-dom'
export default function AdviceNav(){const {pathname}=useLocation();return <nav className="advice-section-nav" aria-label="Advice workspace"><NavLink to="/advice" className={()=>pathname.startsWith('/advice/follow-ups')?'':'active'}>Advice records</NavLink><NavLink to="/advice/follow-ups">Follow-ups</NavLink></nav>}
