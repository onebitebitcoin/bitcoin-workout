import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Building2, Server, Monitor, Database, Container,
  Palette, Code2, Map, ShieldCheck, TrendingUp,
  Megaphone, Wrench, Search, Swords, ChevronLeft,
  type LucideIcon,
} from 'lucide-react'

type AgentCategory = 'build' | 'discuss'

interface Agent {
  name: string
  tools: string[]
  model: string
  category: AgentCategory
  icon: LucideIcon
}

const AGENTS: Agent[] = [
  { name: 'architect', tools: ['Read', 'Grep', 'Glob', 'Bash', 'Write', 'Edit', 'WebFetch', 'WebSearch'], model: 'sonnet', category: 'build', icon: Building2 },
  { name: 'backend', tools: ['Read', 'Grep', 'Glob', 'Bash', 'Write', 'Edit', 'WebFetch'], model: 'sonnet', category: 'build', icon: Server },
  { name: 'frontend', tools: ['Read', 'Grep', 'Glob', 'Bash', 'Write', 'Edit', 'WebFetch'], model: 'sonnet', category: 'build', icon: Monitor },
  { name: 'dba', tools: ['Read', 'Grep', 'Glob', 'Bash', 'Write', 'Edit'], model: 'sonnet', category: 'build', icon: Database },
  { name: 'devops', tools: ['Read', 'Grep', 'Glob', 'Bash', 'Write', 'Edit', 'WebFetch'], model: 'sonnet', category: 'build', icon: Container },
  { name: 'planner', tools: ['Read', 'Grep', 'WebSearch', 'WebFetch', 'Write', 'Edit', 'Bash', 'Glob'], model: 'sonnet', category: 'discuss', icon: Map },
  { name: 'designer', tools: ['Read', 'WebFetch', 'WebSearch', 'Write', 'Glob', 'Grep'], model: 'sonnet', category: 'discuss', icon: Palette },
  { name: 'developer', tools: ['Read', 'Grep', 'Bash', 'WebFetch', 'Write', 'Edit', 'Glob'], model: 'sonnet', category: 'discuss', icon: Code2 },
  { name: 'finance', tools: ['Read', 'Grep', 'WebSearch', 'WebFetch'], model: 'sonnet', category: 'discuss', icon: TrendingUp },
  { name: 'marketing', tools: ['Read', 'WebSearch', 'WebFetch', 'Bash'], model: 'sonnet', category: 'discuss', icon: Megaphone },
  { name: 'ops', tools: ['Read', 'Grep', 'Write', 'Edit', 'Bash', 'WebSearch', 'Glob'], model: 'sonnet', category: 'discuss', icon: Wrench },
  { name: 'qa', tools: ['Read', 'Grep', 'Bash', 'WebSearch', 'Write', 'Edit', 'Glob'], model: 'sonnet', category: 'discuss', icon: ShieldCheck },
  { name: 'researcher', tools: ['Read', 'WebSearch', 'WebFetch', 'Write'], model: 'sonnet', category: 'discuss', icon: Search },
  { name: 'devil', tools: ['Read', 'Grep', 'WebSearch', 'WebFetch'], model: 'sonnet', category: 'discuss', icon: Swords },
]

const BUILD_AGENTS = AGENTS.filter((a) => a.category === 'build')
const DISCUSS_AGENTS = AGENTS.filter((a) => a.category === 'discuss')

function AgentCard({ agent }: { agent: Agent }) {
  const { t } = useTranslation('auth')
  const Icon = agent.icon
  return (
    <div className="rounded-card bg-theme-surface px-4 py-4 flex flex-col gap-3">
      <div className="flex items-start gap-3">
        <div className="mt-1 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-card bg-theme-surface2">
          <Icon size={16} strokeWidth={1.5} className="text-accent" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-body font-semibold text-theme-primary">{t(`agents.${agent.name}.label`)}</span>
            <span className="text-label font-mono text-theme-muted">{agent.name}</span>
          </div>
          <p className="mt-1 text-label text-theme-muted leading-relaxed">{t(`agents.${agent.name}.description`)}</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-1">
        {agent.tools.map((tool) => (
          <span
            key={tool}
            className="rounded-card bg-theme-surface2 px-2 py-1 text-label font-mono text-theme-muted"
          >
            {tool}
          </span>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <span className="text-label text-theme-muted">model</span>
        <span className="text-label font-mono text-accent">{agent.model}</span>
      </div>
    </div>
  )
}

export default function TeamPage() {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()

  return (
    <div className="flex flex-col min-h-[100dvh] bg-theme-page pb-8">
      <div className="flex items-center gap-3 px-4 pt-5 pb-4">
        <button
          onClick={() => navigate(-1)}
          className="text-theme-muted hover:text-theme-primary transition-colors p-1 -ml-1"
          aria-label={t('agentBack')}
        >
          <ChevronLeft size={20} strokeWidth={1.5} />
        </button>
        <div>
          <h1 className="text-title text-theme-primary">{t('teamPageTitle')}</h1>
          <p className="text-label text-theme-muted">{t('teamAgentCount', { count: AGENTS.length })}</p>
        </div>
      </div>

      <div className="px-4 space-y-6">
        <section>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-eyebrow text-theme-muted">
              {t('teamBuild')}
            </span>
            <span className="text-label text-theme-muted">{t('teamBuildCount', { count: BUILD_AGENTS.length })}</span>
          </div>
          <div className="space-y-2">
            {BUILD_AGENTS.map((agent) => (
              <AgentCard key={agent.name} agent={agent} />
            ))}
          </div>
        </section>

        <section>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-eyebrow text-theme-muted">
              {t('teamDiscuss')}
            </span>
            <span className="text-label text-theme-muted">{t('teamDiscussCount', { count: DISCUSS_AGENTS.length })}</span>
          </div>
          <div className="space-y-2">
            {DISCUSS_AGENTS.map((agent) => (
              <AgentCard key={agent.name} agent={agent} />
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
