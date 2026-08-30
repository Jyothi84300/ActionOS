'use client'

import { useMemo, useState } from 'react'
import {
  Activity,
  ArrowLeft,
  ArrowUpRight,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Clock3,
  FileText,
  Gauge,
  Globe2,
  Laptop,
  LockKeyhole,
  Menu,
  MoreHorizontal,
  Plus,
  RotateCcw,
  Settings2,
  ShieldCheck,
  Sparkles,
  Target,
  TerminalSquare,
  Wrench,
  X,
} from 'lucide-react'

type View = 'center' | 'goals' | 'skills' | 'activity' | 'settings'
type GoalStatus = 'Planning' | 'In progress' | 'Waiting' | 'Completed'

type Goal = {
  id: number
  title: string
  detail: string
  due: string
  progress: number
  status: GoalStatus
  color: string
  tasks: number
}

const initialGoals: Goal[] = [
  { id: 1, title: 'Prepare for my interview', detail: 'Senior Product Designer · Luma', due: 'Friday, Jun 14', progress: 42, status: 'In progress', color: 'cobalt', tasks: 5 },
  { id: 2, title: 'Plan a weekend in Copenhagen', detail: 'Food, design, and a little wandering', due: 'Jun 21 – Jun 23', progress: 18, status: 'Planning', color: 'mint', tasks: 4 },
  { id: 3, title: 'Get my tax documents together', detail: '2023 personal filing', due: 'June 30', progress: 76, status: 'Waiting', color: 'amber', tasks: 7 },
]

const activities = [
  ['10:42', 'Interview plan created', 'ActionOS mapped 5 tasks from your goal.', 'plan'],
  ['09:18', 'Permission requested', 'Connect to your calendar to find availability.', 'lock'],
  ['Yesterday', 'Resume review completed', '3 improvements suggested and saved locally.', 'check'],
  ['Mon, Jun 10', 'Goal created', 'Prepare for my interview next Friday.', 'target'],
]

const navItems: { id: View; label: string; icon: typeof Target }[] = [
  { id: 'center', label: 'Action Center', icon: Gauge },
  { id: 'goals', label: 'Goals', icon: Target },
  { id: 'skills', label: 'Skills', icon: Wrench },
  { id: 'activity', label: 'Activity', icon: Activity },
]

function StatusPill({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'active' | 'waiting' | 'complete' }) {
  return <span className={`status-pill ${tone}`}><span className="status-dot" />{children}</span>
}

function ProgressBar({ value, color = 'cobalt' }: { value: number; color?: string }) {
  return <div className="progress-track"><div className={`progress-fill ${color}`} style={{ width: `${value}%` }} /></div>
}

function Sidebar({ view, setView }: { view: View; setView: (v: View) => void }) {
  return <aside className="sidebar">
    <div className="brand"><span className="brand-mark">A</span><span>action<span className="brand-os">os</span></span></div>
    <div className="workspace-switcher"><span className="avatar">JM</span><span className="workspace-name">Jordan&apos;s workspace</span><ChevronRight size={14} /></div>
    <nav className="side-nav" aria-label="Primary navigation">
      <div className="nav-kicker">Workspace</div>
      {navItems.map(({ id, label, icon: Icon }) => <button key={id} className={`nav-item ${view === id ? 'selected' : ''}`} onClick={() => setView(id)}><Icon size={17} />{label}{id === 'center' && <span className="nav-count">2</span>}</button>)}
      <div className="nav-kicker secondary">System</div>
      <button className={`nav-item ${view === 'settings' ? 'selected' : ''}`} onClick={() => setView('settings')}><Settings2 size={17} />Settings</button>
    </nav>
    <div className="sidebar-footer"><div className="connection"><span className="online-dot" /><div><strong>Online</strong><span>All systems operational</span></div></div><div className="user-row"><span className="avatar dark">JM</span><div><strong>Jordan Miller</strong><span>Personal workspace</span></div><MoreHorizontal size={16} /></div></div>
  </aside>
}

function Topbar({ title, onMenu }: { title: string; onMenu: () => void }) {
  return <header className="topbar"><button className="mobile-menu" onClick={onMenu} aria-label="Open navigation"><Menu /></button><div><div className="eyebrow">{title === 'Action Center' ? 'Tuesday, June 11, 2024' : 'Workspace'}</div><h1>{title}</h1></div><div className="top-actions"><button className="icon-button" aria-label="Refresh"><RotateCcw size={17} /></button><button className="avatar top-avatar">JM</button></div></header>
}

function ActionCenter({ goals, onGoal, onNew }: { goals: Goal[]; onGoal: (g: Goal) => void; onNew: (text: string) => void }) {
  const [prompt, setPrompt] = useState('')
  const submit = () => { if (prompt.trim()) { onNew(prompt.trim()); setPrompt('') } }
  return <div className="page-content center-page">
    <section className="hero-block"><div className="eyebrow accent-eyebrow"><Sparkles size={13} />Your action center</div><h2>What do you want<br /><em>to accomplish?</em></h2><p className="hero-copy">Tell me the outcome. I&apos;ll figure out the steps, ask when it matters, and keep you moving.</p>
      <div className="goal-composer"><textarea value={prompt} onChange={e => setPrompt(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) { e.preventDefault(); submit() } }} placeholder="Prepare me for my interview next Friday" aria-label="Describe what you want to accomplish" /><div className="composer-footer"><span><span className="key-hint">⌘</span> + <span className="key-hint">↵</span> to submit</span><button className="submit-button" onClick={submit} aria-label="Create goal"><ArrowUpRight size={19} /></button></div></div>
      <div className="suggestions"><span className="suggestion-label">Try saying</span><button onClick={() => setPrompt('Plan a focused week around my priorities')}>Plan my week <ArrowUpRight size={13} /></button><button onClick={() => setPrompt('Get my tax documents together')}>Gather my documents <ArrowUpRight size={13} /></button><button onClick={() => setPrompt('Find time for a deep work session')}>Find me some time <ArrowUpRight size={13} /></button></div>
    </section>
    <section className="overview-grid"><div className="section-heading"><div><div className="eyebrow">In motion</div><h3>Active goals <span>({goals.length})</span></h3></div><button className="text-button" onClick={() => onGoal(goals[0])}>View all <ArrowUpRight size={14} /></button></div><div className="goal-grid">{goals.slice(0, 3).map(goal => <GoalCard goal={goal} key={goal.id} onClick={() => onGoal(goal)} />)}</div></section>
    <section className="lower-grid"><div><div className="section-heading"><div><div className="eyebrow">Your trail</div><h3>Recent activity</h3></div><button className="text-button">See all <ArrowUpRight size={14} /></button></div><ActivityTimeline compact /></div><div className="system-card"><div className="system-card-header"><div><div className="eyebrow">System status</div><h3>Ready to act</h3></div><span className="pulse-ring"><span /></span></div><p>Everything you need is online. Your local skills are available even without a connection.</p><div className="capability-row"><span><Globe2 size={15} />Online</span><span><Laptop size={15} />Local</span><span><ShieldCheck size={15} />Private</span></div></div></section>
  </div>
}

function GoalCard({ goal, onClick }: { goal: Goal; onClick: () => void }) {
  const tone = goal.status === 'Completed' ? 'complete' : goal.status === 'Waiting' ? 'waiting' : goal.status === 'In progress' ? 'active' : 'neutral'
  return <button className="goal-card" onClick={onClick}><div className={`goal-color ${goal.color}`} /><div className="goal-card-top"><StatusPill tone={tone}>{goal.status}</StatusPill><MoreHorizontal size={16} /></div><h4>{goal.title}</h4><p>{goal.detail}</p><div className="goal-meta"><span><CalendarDays size={14} />{goal.due}</span><span>{goal.tasks} tasks</span></div><ProgressBar value={goal.progress} color={goal.color} /><div className="goal-progress-label"><span>Progress</span><strong>{goal.progress}%</strong></div></button>
}

function ActivityTimeline({ compact = false }: { compact?: boolean }) { return <div className={`activity-list ${compact ? 'compact' : ''}`}>{activities.map(([time, title, text, icon]) => <div className="activity-item" key={title}><div className={`activity-icon ${icon}`}>{icon === 'check' ? <Check size={14} /> : icon === 'lock' ? <LockKeyhole size={13} /> : icon === 'target' ? <Target size={14} /> : <CircleDot size={14} />}</div><div className="activity-copy"><strong>{title}</strong><span>{text}</span></div><time>{time}</time></div>)}</div> }

function GoalDetail({ goal, onBack }: { goal: Goal; onBack: () => void }) {
  const [approved, setApproved] = useState(false)
  return <div className="page-content detail-page"><button className="back-button" onClick={onBack}><ArrowLeft size={16} />Back to action center</button><div className="detail-header"><div><div className="eyebrow accent-eyebrow"><Target size={13} />Goal detail</div><h2>{goal.title}</h2><p>{goal.detail}</p></div><StatusPill tone="active">{approved ? 'Executing' : goal.status}</StatusPill></div><div className="detail-stats"><div><span>Objective</span><strong>Show up prepared and confident</strong></div><div><span>Deadline</span><strong>{goal.due}</strong></div><div><span>Progress</span><strong>{goal.progress}% complete</strong></div></div><div className="detail-columns"><section className="plan-panel"><div className="panel-header"><div><div className="eyebrow">Action plan</div><h3>From intention to done</h3></div><span className="plan-version">v1.0 · just now</span></div><div className="flow"><div className="flow-line" />{[['Understanding','I understand what success looks like.',CheckCircle2],['Context','I found the information I need.',FileText],['Plan','5 tasks mapped to your deadline.',TerminalSquare],['Actions','Ready to work through the plan.',ArrowUpRight],['Verification',"I'll check the result with you.",ShieldCheck]].map(([label, text, Icon], i) => <div className={`flow-step ${i < 3 || approved ? 'done' : i === 3 ? 'current' : ''}`} key={label as string}><div className="flow-icon"><Icon size={16} /></div><div><strong>{label as string}</strong><span>{text as string}</span></div>{i < 3 && <Check size={14} className="step-check" />}</div>)}</div><div className="task-list"><div className="eyebrow">Task sequence</div>{['Review role and company context','Create a focused study guide','Draft answers from your experience','Schedule a practice session','Run final readiness check'].map((task, i) => <div className="task-row" key={task}><span className={`task-number ${i < 2 ? 'done' : ''}`}>{i < 2 ? <Check size={12} /> : i + 1}</span><div><strong>{task}</strong><span>{i === 0 ? 'Document skill · Local' : i === 3 ? 'Calendar skill · Online · Permission needed' : 'ActionOS skill · Local'}</span></div><StatusPill tone={i < 2 ? 'complete' : i === 3 && !approved ? 'waiting' : 'neutral'}>{i < 2 ? 'Done' : i === 3 && !approved ? 'Needs approval' : 'Queued'}</StatusPill></div>)}</div></section><aside className="side-panel"><div className="permission-card"><div className="permission-icon"><LockKeyhole size={17} /></div><div className="eyebrow">Permission needed</div><h3>Connect your calendar?</h3><p>ActionOS wants to find a 45-minute window for a practice session this week.</p><div className="permission-detail"><span>Service</span><strong>Google Calendar</strong><span>Access</span><strong>Read availability only</strong></div>{approved ? <div className="approved-state"><Check size={15} />Confirmed — action is running</div> : <div className="permission-actions"><button className="button primary" onClick={() => setApproved(true)}>Approve & continue</button><button className="button ghost">Edit plan</button></div>}</div><div className="capabilities-card"><div className="eyebrow">Capabilities</div><div><Laptop size={16} /><span>Local skills <strong>3 available</strong></span></div><div><Globe2 size={16} /><span>Online skills <strong>2 available</strong></span></div><div><ShieldCheck size={16} /><span>Data handling <strong>Private by default</strong></span></div></div></aside></div></div>
}

function SkillsView() { const skills = [['Document','1.4.2','Read, write, summarize, and transform documents',FileText,'Local'],['Task','1.1.0','Create, update, and track action items',CheckCircle2,'Local'],['Calendar','2.0.1','Find availability and schedule events',CalendarDays,'Online']]; return <div className="page-content"><div className="view-intro"><div><div className="eyebrow">Extend what&apos;s possible</div><h2>Skills</h2><p>ActionOS uses focused skills to turn your intent into useful work.</p></div><button className="button primary"><Plus size={16} />Add a skill</button></div><div className="skills-list">{skills.map(([name, version, description, Icon, status]) => <div className="skill-row" key={name as string}><div className="skill-icon"><Icon size={19} /></div><div className="skill-info"><h3>{name as string}</h3><p>{description as string}</p></div><span className="version">v{version as string}</span><StatusPill tone="complete">{status as string}</StatusPill><ChevronRight size={17} /></div>)}</div></div> }
function ActivityView() { return <div className="page-content"><div className="view-intro"><div><div className="eyebrow">A clear trail</div><h2>Activity</h2><p>Every decision, permission, and completed action in one place.</p></div><button className="button ghost"><RotateCcw size={15} />Refresh</button></div><div className="activity-panel"><ActivityTimeline /></div></div> }
function SettingsView() { return <div className="page-content"><div className="view-intro"><div><div className="eyebrow">Make it yours</div><h2>Settings</h2><p>Control how ActionOS thinks, acts, and handles your data.</p></div></div><div className="settings-list">{[['AI preference','Balanced · ActionOS chooses the right model for the task',Sparkles],['Permissions','Ask before any external action',LockKeyhole],['Privacy','Local-first · Never sell or train on your data',ShieldCheck],['Availability','Online with local fallback',Globe2],['Notifications','Important updates only',Activity]].map(([title, detail, Icon]) => <button className="setting-row" key={title as string}><div className="setting-icon"><Icon size={17} /></div><div><strong>{title as string}</strong><span>{detail as string}</span></div><ChevronRight size={17} /></button>)}</div></div> }

export default function ActionOSWorkspace() {
  const [view, setView] = useState<View>('center'); const [goals, setGoals] = useState(initialGoals); const [selectedGoal, setSelectedGoal] = useState<Goal | null>(null); const [mobileOpen, setMobileOpen] = useState(false)
  const createGoal = (text: string) => { const goal = { id: Date.now(), title: text, detail: 'New goal · needs a little context', due: 'No deadline yet', progress: 8, status: 'Planning' as GoalStatus, color: 'cobalt', tasks: 0 }; setGoals(g => [goal, ...g]); setSelectedGoal(goal) }
  const title = selectedGoal ? 'Goal detail' : navItems.find(n => n.id === view)?.label ?? 'Settings'
  return <div className="app-shell"><div className={`mobile-drawer ${mobileOpen ? 'open' : ''}`}><Sidebar view={view} setView={v => { setView(v); setMobileOpen(false) }} /></div><Sidebar view={view} setView={v => { setView(v); setSelectedGoal(null) }} /><main className="main"><Topbar title={title} onMenu={() => setMobileOpen(true)} />{selectedGoal ? <GoalDetail goal={selectedGoal} onBack={() => setSelectedGoal(null)} /> : view === 'center' ? <ActionCenter goals={goals} onGoal={setSelectedGoal} onNew={createGoal} /> : view === 'goals' ? <div className="page-content"><div className="view-intro"><div><div className="eyebrow">Everything in motion</div><h2>Goals</h2><p>Outcomes you&apos;ve asked ActionOS to move forward.</p></div><button className="button primary" onClick={() => setView('center')}><Plus size={16} />New goal</button></div><div className="goal-grid all-goals">{goals.map(g => <GoalCard goal={g} key={g.id} onClick={() => setSelectedGoal(g)} />)}</div></div> : view === 'skills' ? <SkillsView /> : view === 'activity' ? <ActivityView /> : <SettingsView />}</main></div>
}
