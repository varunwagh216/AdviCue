import { useState, type FormEvent } from 'react'
import { ArrowRight, Eye, EyeOff } from 'lucide-react'
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
        <h1>See what<br/><em>others miss.</em></h1>
        <p>Every client in focus. Every next step clear.</p>
      </div>
      <div className="login-decor deco-1"/><div className="login-decor deco-2"/>
    </div>
    <div className="login-right">
      <div className="login-form-container">
        <h2>Welcome back</h2>
        <form onSubmit={submit} className="login-form">
          <label htmlFor="email">Email address</label>
          <input id="email" type="email" autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)} placeholder="advisor@advicue.local" required />
          <label htmlFor="password">Password</label>
          <div className="password-field"><input id="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="Enter your password" required /><button type="button" aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword} onClick={()=>setShowPassword(!showPassword)}>{showPassword ? <EyeOff size={18}/> : <Eye size={18}/>}</button></div>
          {error && <div className="login-error" role="alert">{error}</div>}
          <button className="sign-in-button" type="submit" disabled={loading}>{loading ? 'Signing in…' : 'Sign in'} <ArrowRight size={18}/></button>
        </form>
      </div>
    </div>
  </div>
}
