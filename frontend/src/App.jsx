import React, { useState, useEffect } from 'react'
import { api } from './api'
import Search from './Search'
import Services from './Services'
import Entries from './Entries'
import Upload from './Upload'
import './App.css'

const TABS = [
  { id: 'search', label: 'Search', icon: '🔍' },
  { id: 'entries', label: 'RCA / Runbook', icon: '📋' },
  { id: 'services', label: 'Services', icon: '⚙️' },
  { id: 'upload', label: 'RCA by file', icon: '📄' },
]

export default function App() {
  const [tab, setTab] = useState('search')
  const [services, setServices] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.services.list()
      .then(setServices)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const refreshServices = () => api.services.list().then(setServices)

  return (
    <div className="app">
      <header className="header">
        <h1>CRM On-Call Assistant</h1>
        <p className="tagline">Search runbooks, add or update RCAs via UI or file</p>
      </header>
      <nav className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`tab ${tab === t.id ? 'active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            <span className="tab-icon">{t.icon}</span>
            {t.label}
          </button>
        ))}
      </nav>
      {error && (
        <div className="banner error">
          Backend not reachable: {error}. Start the backend with <code>cd backend && uvicorn app.main:app --reload</code>
        </div>
      )}
      <main className="main">
        {loading && tab === 'services' ? (
          <div className="loading">Loading services…</div>
        ) : (
          <>
            {tab === 'search' && <Search services={services} />}
            {tab === 'entries' && <Entries services={services} onServiceChange={refreshServices} />}
            {tab === 'services' && <Services services={services} onUpdate={refreshServices} />}
            {tab === 'upload' && <Upload services={services} onUploaded={refreshServices} />}
          </>
        )}
      </main>
    </div>
  )
}
