import { useState, type FormEvent } from 'react'
import { ArrowRight, Eye, EyeOff, LockKeyhole, Radar, ShieldCheck, Sparkles } from 'lucide-react'
import { Navigate, useNavigate } from 'react-router-dom'
import Brand from '../components/Brand'
import { useAuth } from '../context/AuthContext'
import { humanError } from '../lib/api'

export default function Login() {
  const { user, login } = useAuth()
  const [email, setEmail] = useState('advisor@advicue.local')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()
  if (user) return <Navigate to="/" replace />

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try { await login(email, password); navigate('/', { replace: true }) }
    catch (err) { setError(humanError(err)) }
    finally { setLoading(false) }
  }

  return <div className="login-page">
    <div className="login-left">
      <div className="login-left-top"><Brand/></div>
      <div className="login-story">
        <div className="story-chip"><Sparkles size={14}/> INTELLIGENCE FOR EVERY CLIENT</div>
        <h1>See what<br/><em>others miss.</em></h1>
        <p>An advisor workspace designed to surface overlooked clients, explain the evidence, and close the loop on every recommendation.</p>
        <div className="story-features">
          <div><div className="story-feature-icon"><Radar size={21}/></div><span>Detect meaningful portfolio patterns</span></div>
          <div><div className="story-feature-icon"><ShieldCheck size={21}/></div><span>Make evidence-backed decisions</span></div>
          <div><div className="story-feature-icon"><LockKeyhole size={21}/></div><span>Track advice with accountability</span></div>
        </div>
      </div>
      <div className="login-left-bottom">AdviCue AI <span>•</span> Spot What Matters. Act Smarter.</div>
      <div className="login-decor deco-1"/><div className="login-decor deco-2"/>
    </div>
    <div className="login-right">
      <div className="login-form-container">
        <div className="login-top-icon"><LockKeyhole size={23}/></div>
        <div className="login-eyebrow">WELCOME BACK</div>
        <h2>Sign in to your workspace</h2>
        <p className="login-intro">Enter your account credentials to access your workspace.</p>
        <form onSubmit={submit} className="login-form">
          <label htmlFor="email">Email address</label>
          <input id="email" type="email" autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)} placeholder="advisor@advicue.local" required />
          <label htmlFor="password">Password</label>
          <div className="password-field"><input id="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="Enter your password" required /><button type="button" title="Show/hide password" onClick={()=>setShowPassword(!showPassword)}>{showPassword ? <EyeOff size={18}/> : <Eye size={18}/>}</button></div>
          {error && <div className="login-error" role="alert">{error}</div>}
          <button className="sign-in-button" type="submit" disabled={loading}>{loading ? 'Signing in…' : 'Sign in to workspace'} <ArrowRight size={18}/></button>
        </form>
        <div className="login-hint"><ShieldCheck size={16}/><span>Offline advisor workspace · Financial records remain on this computer.</span></div>
      </div>
      <div className="login-bottom-info">Secure access <span>·</span> Built with Llama</div>
    </div>
  </div>
}
