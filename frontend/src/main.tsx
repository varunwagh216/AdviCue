import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import App from './App'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider><App/></AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
)

import './wealth-desk.css'

import './concept-board.css'

import './focused-workspace.css'

import './workspace.css'

import './product-experience.css'
import './prototype-match.css'
import './complete-experience.css'
import './navy-refinement.css'
import './pattern-workspace.css'

import './login-refinement.css'

import './brand-refinement.css'
