import { useState, type FormEvent } from 'react'
import { ArrowRight, LockKeyhole, Radar, ShieldCheck, Sparkles } from 'lucide-react'
import { Navigate, useNavigate } from 'react-router-dom'
import Brand from '../components/Brand'
import { useAuth } from '../context/AuthContext'
import { humanError } from '../lib/api'

export default function Login() {
  const { user, login } = useAuth()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()
  if (user) return <Navigate to="/" replace />

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try { await login(); navigate('/', { replace: true }) }
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
        <h2>Your advisor workspace</h2>
        <p className="login-intro">Open your local workspace to review clients, advice and follow-ups.</p>
        <form onSubmit={submit} className="login-form">
          {error && <div className="login-error" role="alert">{error}</div>}
          <button className="sign-in-button" type="submit" disabled={loading}>{loading ? 'Opening workspace…' : 'Enter AdviCue'} <ArrowRight size={18}/></button>
        </form>
        <div className="login-hint"><ShieldCheck size={16}/><span>Offline advisor workspace · Financial records remain on this computer.</span></div>
      </div>
      <div className="login-bottom-info">Local access <span>·</span> Built with Llama</div>
    </div>
  </div>
}
