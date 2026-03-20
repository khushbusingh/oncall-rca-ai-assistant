import React, { useState, useEffect } from 'react'
import { api } from './api'

export default function Entries({ services, onServiceChange }) {
  const [entries, setEntries] = useState([])
  const [filterServiceId, setFilterServiceId] = useState('')
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState(null) // null | 'create' | { type: 'edit', entry }
  const [form, setForm] = useState({ service_id: '', title: '', description: '', solution: '' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const load = () => {
    setLoading(true)
    api.entries.list(filterServiceId ? parseInt(filterServiceId, 10) : null)
      .then(setEntries)
      .catch(() => setEntries([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => load(), [filterServiceId])

  const openCreate = () => {
    setModal('create')
    setForm({
      service_id: services[0]?.id?.toString() || '',
      title: '',
      description: '',
      solution: '',
    })
    setError(null)
  }

  const openEdit = (e) => {
    setModal({ type: 'edit', entry: e })
    setForm({
      service_id: String(e.service_id),
      title: e.title,
      description: e.description || '',
      solution: e.solution || '',
    })
    setError(null)
  }

  const close = () => {
    setModal(null)
    setError(null)
  }

  const save = async () => {
    if (!form.title.trim()) return
    const payload = {
      service_id: parseInt(form.service_id, 10),
      title: form.title.trim(),
      description: form.description.trim() || null,
      solution: form.solution.trim() || null,
    }
    setSaving(true)
    setError(null)
    try {
      if (modal === 'create') {
        await api.entries.create(payload)
      } else {
        await api.entries.update(modal.entry.id, payload)
      }
      load()
      onServiceChange()
      close()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const deleteEntry = async (id) => {
    if (!confirm('Delete this entry?')) return
    try {
      await api.entries.delete(id)
      load()
      close()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <>
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1rem' }}>
          <h2>RCA / Runbook entries</h2>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <select
              value={filterServiceId}
              onChange={(e) => setFilterServiceId(e.target.value)}
              className="btn"
              style={{ minWidth: '160px' }}
            >
              <option value="">All services</option>
              {services.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
            <button className="btn primary" onClick={openCreate}>Add RCA</button>
          </div>
        </div>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1rem' }}>
          Add or update RCAs here (via UI), or upload a document in the <strong>RCA by file</strong> tab.
        </p>
        {loading ? (
          <div className="loading">Loading…</div>
        ) : entries.length === 0 ? (
          <div className="empty">No RCAs yet. Add one here or upload a file in the RCA by file tab.</div>
        ) : (
          <div>
            {entries.map((e) => (
              <div key={e.id} className="list-item">
                <div className="list-item-content" style={{ flex: 1 }}>
                  <h3>{e.title}</h3>
                  <p>{e.description || '—'} · Service ID: {e.service_id}</p>
                  {e.solution && (
                    <p style={{ marginTop: '0.5rem', fontSize: '0.85rem', whiteSpace: 'pre-wrap' }}>{e.solution.slice(0, 200)}{e.solution.length > 200 ? '…' : ''}</p>
                  )}
                </div>
                <div className="list-item-actions">
                  <button className="btn" onClick={() => openEdit(e)}>Edit RCA</button>
                  <button className="btn danger" onClick={() => deleteEntry(e.id)}>Delete</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      {modal && (
        <div className="modal-overlay" onClick={close}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>{modal === 'create' ? 'Add RCA' : 'Edit RCA'}</h2>
            {error && <div className="banner error">{error}</div>}
            <div className="form-group">
              <label>Service</label>
              <select
                value={form.service_id}
                onChange={(e) => setForm((f) => ({ ...f, service_id: e.target.value }))}
              >
                {services.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>Title</label>
              <input
                value={form.title}
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                placeholder="e.g. Payment timeout in checkout"
              />
            </div>
            <div className="form-group">
              <label>Description / Symptoms</label>
              <textarea
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                placeholder="What happens, error messages, etc."
              />
            </div>
            <div className="form-group">
              <label>Solution / Steps</label>
              <textarea
                value={form.solution}
                onChange={(e) => setForm((f) => ({ ...f, solution: e.target.value }))}
                placeholder="Step-by-step resolution"
              />
            </div>
            <div className="form-actions">
              <button className="btn primary" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
              <button className="btn" onClick={close}>Cancel</button>
              {modal !== 'create' && (
                <button className="btn danger" onClick={() => deleteEntry(modal.entry.id)}>Delete</button>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
