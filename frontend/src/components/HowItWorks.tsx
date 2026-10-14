import { useEffect, useRef } from 'react'

// The pipeline in four steps: [agent, what it does in a few words].
const AGENTS: [name: string, does: string][] = [
  ['Analyst', 'gets the numbers from stats tools, over MCP'],
  ['Retrieval', 'finds similar moments elsewhere'],
  ['Narrator', 'writes the recap'],
  ['Verifier', 'checks every sentence'],
]

// Generic line icons (not product logos): what each service does for this app.
const ICONS = {
  agents:
    'M6 7a2 2 0 1 0 0-4 2 2 0 0 0 0 4zm12 0a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM12 21a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM7.5 6.5l3.5 10M16.5 6.5L13 16.5M8 5h8',
  ai: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z',
  database:
    'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zm0 0v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
  box: 'M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5',
  globe:
    'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z',
  chart: 'M4 20h16M6 16l4-5 3 3 5-7',
  plug: 'M9 3v5M15 3v5M7 8h10v4a5 5 0 0 1-10 0zM12 17v4',
  branch: 'M6 3v12M6 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM18 9c0 4-6 4-12 6',
}

const TECH: { name: string; role: string; icon: keyof typeof ICONS; docs: string }[] = [
  {
    name: 'Microsoft Agent Framework',
    role: 'agents + workflow',
    icon: 'agents',
    docs: 'https://github.com/microsoft/agent-framework',
  },
  {
    name: 'Microsoft Foundry',
    role: 'models + tracing',
    icon: 'ai',
    docs: 'https://learn.microsoft.com/azure/ai-foundry/',
  },
  {
    name: 'Azure Cosmos DB',
    role: 'data + vector search',
    icon: 'database',
    docs: 'https://learn.microsoft.com/azure/cosmos-db/nosql/vector-search',
  },
  {
    name: 'Azure Container Apps',
    role: 'the API',
    icon: 'box',
    docs: 'https://learn.microsoft.com/azure/container-apps/',
  },
  {
    name: 'Azure Static Web Apps',
    role: 'this page',
    icon: 'globe',
    docs: 'https://learn.microsoft.com/azure/static-web-apps/',
  },
  {
    name: 'Application Insights',
    role: 'monitoring',
    icon: 'chart',
    docs: 'https://learn.microsoft.com/azure/azure-monitor/app/app-insights-overview',
  },
  {
    name: 'Model Context Protocol',
    role: 'stats tools server',
    icon: 'plug',
    docs: 'https://modelcontextprotocol.io/',
  },
  { name: 'GitHub Actions', role: 'tests + deploys', icon: 'branch', docs: 'https://docs.github.com/actions' },
]

const TRY: string[] = [
  'Click any sentence to see its proof on the pitch and in the panel.',
  'Switch to Live and press Watch: verified commentary, minute by minute.',
  'Open Personalize: another voice, language, your club, or Compare side by side.',
]

/** A short guide for first-time visitors and judges: what this is, how it works, and what to try. */
export function HowItWorks({ open, onClose }: { open: boolean; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const d = dialog.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])

  return (
    <dialog
      ref={dialog}
      className="how-it-works"
      aria-labelledby="how-title"
      onClose={onClose}
      onClick={(e) => e.target === dialog.current && onClose()} // a click on the backdrop closes it
    >
      <div className="how-body">
        <header className="how-header">
          <h2 id="how-title">How it works</h2>
          <button type="button" className="icon-button" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        </header>

        <p className="how-lead">
          AI agents turn synthetic match events into recaps where <strong>every sentence links to its proof</strong>.
          Numbers come from code, words from AI, and anything unproven is rewritten or removed.
        </p>

        <ol className="how-flow">
          {AGENTS.map(([name, does]) => (
            <li key={name}>
              <strong>{name}</strong>
              <span>{does}</span>
            </li>
          ))}
        </ol>

        <h3>Try this</h3>
        <ol className="how-try">
          {TRY.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>

        <h3>Built with</h3>
        <ul className="how-chips">
          {TECH.map((t) => (
            <li key={t.name}>
              <a href={t.docs} target="_blank" rel="noreferrer">
                <svg
                  viewBox="0 0 24 24"
                  width="15"
                  height="15"
                  aria-hidden="true"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d={ICONS[t.icon]} />
                </svg>
                <span className="how-chip-name">{t.name}</span>
                <span className="how-chip-role">{t.role}</span>
              </a>
            </li>
          ))}
        </ul>
      </div>
    </dialog>
  )
}
