import { useId } from 'react'

export default function Brand(){
  const id=useId()
  return <div className="brand-lockup"><svg className="brand-symbol" viewBox="0 0 64 58" aria-hidden="true" focusable="false"><defs><linearGradient id={id+'-cyan'} x1="0" y1="1" x2="1" y2="0"><stop stopColor="#71f9eb"/><stop offset="1" stopColor="#20bedf"/></linearGradient><linearGradient id={id+'-blue'} x1="0" y1="0" x2="1" y2="1"><stop stopColor="#0386ad"/><stop offset="1" stopColor="#27d8f4"/></linearGradient></defs><path d="M32 2 2 56h13L38 14Z" fill={'url(#'+id+'-cyan)'}/><path d="m32 2 30 54H49L26 15Z" fill={'url(#'+id+'-blue)'}/><path d="m32 2 6 12-7 12-6-11Z" fill="#50e6e5"/><path d="m27 38 10 18H22l-4-7Z" fill="#20cfe7"/><path d="m27 38 6 11H18Z" fill="#087eaa"/></svg><div className="brand-name">AdviCue <span>AI</span></div></div>
}
