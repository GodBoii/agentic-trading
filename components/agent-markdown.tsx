import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export default function AgentMarkdown({
    children,
    tone = 'default',
}: {
    children?: string | null
    tone?: 'default' | 'danger'
}) {
    if (!children) return null

    return (
        <div className={`agent-markdown ${tone === 'danger' ? 'agent-markdown-danger' : ''}`}>
            <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                    a: ({ href, children: linkChildren }) => (
                        <a href={href} target="_blank" rel="noreferrer">
                            {linkChildren}
                        </a>
                    ),
                    table: ({ children: tableChildren }) => (
                        <div className="agent-markdown-table">
                            <table>{tableChildren}</table>
                        </div>
                    ),
                }}
            >
                {children}
            </ReactMarkdown>
        </div>
    )
}
