import { useEffect, useState } from 'react';
import { Activity } from 'lucide-react';
import { api } from './api';

type Row = {
  id: number; attempt_id: number; student: string; student_id?: string; exam: string;
  activity_type: string; details: Record<string, any>; occurred_at: string;
};

const labels: Record<string, string> = {
  attempt_started: 'Started examination', answer_saved: 'Saved answer',
  exam_submitted: 'Submitted examination', proctoring_event: 'Proctoring signal',
  attempt_paused: 'Attempt paused for review',
};

function detail(row: Row) {
  const d = row.details || {};
  if (row.activity_type === 'answer_saved') return `Question ${d.question_id} · ${d.answered ? 'answered' : 'cleared'}`;
  if (row.activity_type === 'proctoring_event') return `${String(d.event_type || '').replaceAll('_', ' ')} · warning ${d.warning_number}`;
  if (row.activity_type === 'exam_submitted') return `Score ${d.score}/${d.max_score}${d.manual_review_required ? ' · written answer review' : ''}`;
  return d.reason ? String(d.reason).replaceAll('_', ' ') : '—';
}

export default function StudentActivityLog() {
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    const load = () => api.get('/admin/activity').then(({ data }) => {
      if (active) { setRows(data); setError(''); }
    }).catch(() => { if (active) setError('Unable to load student activity. Check admin access and the backend.'); });
    load();
    const timer = window.setInterval(load, 2000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  return <>
    <div className="page-title"><div><span className="section-kicker">AUDIT TRAIL</span><h1>Student activity</h1><p>Exam actions and proctoring signals refresh every 2 seconds. Answer content and camera frames are never included.</p></div></div>
    <div className="surface table-surface">
      <div className="table-toolbar"><div><b>Recent activity</b><small>{rows.length} recorded actions · newest first</small></div><span className="local-badge"><i/> LIVE</span></div>
      {error && <div className="error-box">{error}</div>}
      <table><thead><tr><th>STUDENT</th><th>EXAMINATION</th><th>ACTIVITY</th><th>DETAILS</th><th>TIME</th></tr></thead>
        <tbody>{rows.map(row => <tr key={row.id}>
          <td><b>{row.student}</b><small>{row.student_id || 'Student'} · Attempt {row.attempt_id}</small></td>
          <td>{row.exam}</td><td><span className="status-pill available">{labels[row.activity_type] || row.activity_type.replaceAll('_', ' ')}</span></td>
          <td>{detail(row)}</td><td>{new Date(row.occurred_at).toLocaleString()}</td>
        </tr>)}</tbody>
      </table>
      {!rows.length && !error && <div className="empty-state"><Activity/><h3>No student activity yet</h3><p>Attempt starts, answer saves, submissions and proctoring signals will appear here.</p></div>}
    </div>
  </>;
}
