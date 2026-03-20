import React, { useState } from 'react'

const CHUNKS_COLLAPSED_DEFAULT = true
import { api } from './api'

export default function Search({ services }) {
  const [query, setQuery] = useState('')
  const [serviceId, setServiceId] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [chunksExpanded, setChunksExpanded] = useState(!CHUNKS_COLLAPSED_DEFAULT)

  const handleSearch = async (e) => {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    setChunksExpanded(!CHUNKS_COLLAPSED_DEFAULT)
    try {
      const res = await api.search({
        query: query.trim(),
        service_id: serviceId ? parseInt(serviceId, 10) : null,
        top_k: 6,
      })
      setResult(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <h2>Search knowledge base</h2>
      <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1rem' }}>
        Ask in natural language. Results are retrieved from uploaded docs and manual entries. Optionally filter by service.
      </p>
      <form onSubmit={handleSearch} className="search-box">
        <input
          type="text"
          placeholder="e.g. Payment failure in sa-myntra, how to restart service..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={loading}
        />
        <select
          value={serviceId}
          onChange={(e) => setServiceId(e.target.value)}
          disabled={loading}
        >
          <option value="">All services</option>
          {services.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
        <button type="submit" className="btn primary" disabled={loading}>
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>
      {error && <div className="banner error">{error}</div>}
      {result && (
        <>
          {result.answer && (
            <div className="search-answer">
              {(() => {
                const serviceNames = [...new Set((result.chunks || []).map((c) => c.metadata?.service_name).filter(Boolean))]
                return (
                  <>
                    {serviceNames.length > 0 && (
                      <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
                        Source: {serviceNames.join(', ')}
                      </div>
                    )}
                    <strong>Answer:</strong><br />
                    {result.answer}
                  </>
                )
              })()}
            </div>
          )}
          <div style={{ marginTop: '1rem' }}>
            <button
              type="button"
              onClick={() => setChunksExpanded((e) => !e)}
              style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--text)', fontSize: '1rem', fontWeight: 'bold' }}
            >
              Relevant chunks ({result.chunks?.length || 0}) {chunksExpanded ? '▼' : '▶'}
            </button>
            {chunksExpanded && (result.chunks || []).map((c, i) => (
              <div key={i} className="search-result-chunk" style={{ marginTop: i > 0 ? '0.5rem' : '0.5rem', paddingTop: i > 0 ? '0.5rem' : 0, borderTop: i > 0 ? '1px solid #ddd' : 'none', fontSize: '0.9rem' }}>
                {c.metadata?.service_name && (
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>From: {c.metadata.service_name}</div>
                )}
                {c.document}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
