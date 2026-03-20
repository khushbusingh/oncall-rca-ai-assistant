import React, { useState } from 'react'
import { api } from './api'

export default function Services({ services, onUpdate }) {
  const [modal, setModal] = useState(null) // 'create' | { type: 'edit', service }
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const openCreate = () => {
    setModal('create')
    setName('')
    setDescription('')
    setError(null)
  }

  const openEdit = (s) => {
    setModal({ type: 'edit', service: s })
    setName(s.name)
    setDescription(s.description || '')
    setError(null)
  }

  const close = () => {
    setModal(null)
    setError(null)
  }

  const save = async () => {
    if (!name.trim()) return
    setSaving(true)
    setError(null)
    try {
      if (modal === 'create') {
        await api.services.create({ name: name.trim(), description: description.trim() || null })
      } else {
        await api.services.update(modal.service.id, { name: name.trim(), description: description.trim() || null })
      }
      onUpdate()
      close()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const deleteService = async (id) => {
    if (!confirm('Delete this service? Entries under it may need to be reassigned.')) return
    try {
      await api.services.delete(id)
      onUpdate()
      close()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <>
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2>Services</h2>
          <button className="btn primary" onClick={openCreate}>Add service</button>
        </div>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1rem' }}>
          Each CRM service (e.g. sa-myntra, spectrum-server) can have its own runbooks and uploaded docs.
        </p>
        {services.length === 0 ? (
          <div className="empty">No services yet. Add one to start.</div>
        ) : (
          <div>
            {services.map((s) => (
              <div key={s.id} className="list-item">
                <div className="list-item-content">
                  <h3>{s.name}</h3>
                  {s.description && <p>{s.description}</p>}
                </div>
                <div className="list-item-actions">
                  <button className="btn" onClick={() => openEdit(s)}>Edit</button>
                  <button className="btn danger" onClick={() => deleteService(s.id)}>Delete</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      {modal && (
        <div className="modal-overlay" onClick={close}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>{modal === 'create' ? 'Add service' : 'Edit service'}</h2>
            {error && <div className="banner error">{error}</div>}
            <div className="form-group">
              <label>Name</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. sa-myntra" />
            </div>
            <div className="form-group">
              <label>Description (optional)</label>
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Short description" />
            </div>
            <div className="form-actions">
              <button className="btn primary" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
              <button className="btn" onClick={close}>Cancel</button>
              {modal !== 'create' && (
                <button className="btn danger" onClick={() => deleteService(modal.service.id)}>Delete</button>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
