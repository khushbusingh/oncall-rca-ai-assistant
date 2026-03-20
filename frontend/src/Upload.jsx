import React, { useState } from 'react'
import { api } from './api'

export default function Upload({ services, onUploaded }) {
  const [serviceId, setServiceId] = useState(services[0]?.id?.toString() || '')
  const [file, setFile] = useState(null)
  const [updateExisting, setUpdateExisting] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!file || !serviceId) {
      setError('Select a service and a PDF or DOCX file.')
      return
    }
    const ext = (file.name || '').toLowerCase()
    if (!ext.endsWith('.pdf') && !ext.endsWith('.docx') && !ext.endsWith('.doc')) {
      setError('Only PDF and DOCX files are supported.')
      return
    }
    setUploading(true)
    setError(null)
    setMessage(null)
    try {
      const res = await api.upload(file, parseInt(serviceId, 10), updateExisting)
      setMessage(updateExisting
        ? `Added new version of "${file.name}" (${res.chunks} chunks). Previous data kept. Search uses latest version.`
        : `Uploaded "${file.name}". Ingested ${res.chunks} chunks. They are now searchable.`)
      setFile(null)
      onUploaded()
    } catch (e) {
      setError(e.message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="card">
      <h2>Add or update RCA by file</h2>
      <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1rem' }}>
        Upload a runbook or RCA document (PDF/DOC/DOCX). Content is chunked and indexed. No existing data is deleted: re-upload with the same service + filename and check “New version” to add an updated version; search always uses the latest version.
      </p>
      {services.length === 0 ? (
        <div className="empty">Add a service first (Services tab).</div>
      ) : (
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Service</label>
            <select
              value={serviceId}
              onChange={(e) => setServiceId(e.target.value)}
            >
              {services.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label>File (PDF, DOC, or DOCX)</label>
            <input
              type="file"
              accept=".pdf,.docx,.doc"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </div>
          <div className="form-group" style={{ flexDirection: 'row', alignItems: 'center', gap: '0.5rem' }}>
            <input
              type="checkbox"
              id="update-existing-upload"
              checked={updateExisting}
              onChange={(e) => setUpdateExisting(e.target.checked)}
            />
            <label htmlFor="update-existing-upload" style={{ marginBottom: 0 }}>This is a new version of an existing document (same service + filename); keep previous data</label>
          </div>
          {message && <div className="banner" style={{ background: 'rgba(63, 185, 80, 0.15)', borderColor: 'var(--success)' }}>{message}</div>}
          {error && <div className="banner error">{error}</div>}
          <div className="form-actions">
            <button type="submit" className="btn primary" disabled={uploading}>
              {uploading ? 'Uploading…' : updateExisting ? 'Add new version' : 'Upload & index'}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
