import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

// Development only. In production the simulator calls its own origin and nginx
// injects the webhook secret server-side, because anything inlined here ends up
// readable in the public JavaScript bundle.
const WEBHOOK_SECRET = import.meta.env.VITE_WEBHOOK_SECRET

const STORAGE_KEY_FROM = 'sms-simulator.from'
const STORAGE_KEY_TO = 'sms-simulator.to'
const STORAGE_KEY_RECENT_FROM = 'sms-simulator.recent-from'
const STORAGE_KEY_RECENT_TO = 'sms-simulator.recent-to'

const MAX_RECENT = 10

// localStorage throws in private-browsing modes, so fall back to the default.
function loadStoredNumber(key, fallback) {
    try {
        return localStorage.getItem(key) ?? fallback
    } catch {
        return fallback
    }
}

function storeNumber(key, value) {
    try {
        localStorage.setItem(key, value)
    } catch {
        // Persistence is a convenience; ignore quota/permission failures.
    }
}

// Anything could be sitting under these keys -- a half-written value, or a
// string from an older build -- so validate rather than trust the shape.
function loadStoredNumbers(key) {
    try {
        const parsed = JSON.parse(localStorage.getItem(key))
        if (!Array.isArray(parsed)) return []
        return parsed
            .filter(value => typeof value === 'string' && value.trim())
            .slice(0, MAX_RECENT)
    } catch {
        return []
    }
}

function storeNumbers(key, values) {
    try {
        localStorage.setItem(key, JSON.stringify(values))
    } catch {
        // Without storage the list still works, just for this session only.
    }
}

// Most recent first, no duplicates, capped.
function addRecentNumber(values, value) {
    const trimmed = value.trim()
    if (!trimmed) return values
    return [trimmed, ...values.filter(v => v !== trimmed)].slice(0, MAX_RECENT)
}

function initialsFromNumber(value) {
    const digits = String(value).replace(/\D/g, '')
    if (digits.length >= 2) return digits.slice(-2)
    return '•'
}

export default function App() {
    const [from, setFrom] = useState(() =>
        loadStoredNumber(STORAGE_KEY_FROM, '+15551234567')
    )
    const [to, setTo] = useState(() =>
        loadStoredNumber(STORAGE_KEY_TO, '+15559876543')
    )
    const [recentFrom, setRecentFrom] = useState(() =>
        loadStoredNumbers(STORAGE_KEY_RECENT_FROM)
    )
    const [recentTo, setRecentTo] = useState(() =>
        loadStoredNumbers(STORAGE_KEY_RECENT_TO)
    )
    const [body, setBody] = useState('')
    const [messages, setMessages] = useState([])
    const [loading, setLoading] = useState(false) // new state for progress indicator
    const chatRef = useRef(null)

    // Follow the conversation down as it grows. The typewriter rewrites the last
    // message on every tick, so this also keeps a long reply in view while it
    // types rather than only once it finishes.
    useEffect(() => {
        const chat = chatRef.current
        if (chat) chat.scrollTop = chat.scrollHeight
    }, [messages])

    useEffect(() => {
        storeNumber(STORAGE_KEY_FROM, from)
    }, [from])

    useEffect(() => {
        storeNumber(STORAGE_KEY_TO, to)
    }, [to])

    // Called once the webhook has accepted the message, so the lists only ever
    // fill up with pairs that actually reached a group.
    function rememberNumbers() {
        const nextFrom = addRecentNumber(recentFrom, from)
        setRecentFrom(nextFrom)
        storeNumbers(STORAGE_KEY_RECENT_FROM, nextFrom)

        const nextTo = addRecentNumber(recentTo, to)
        setRecentTo(nextTo)
        storeNumbers(STORAGE_KEY_RECENT_TO, nextTo)
    }

    async function sendMessage() {
        if (!body.trim()) return

        const payload = { from, to, body }

        // optimistic UI update
        setMessages(m => [...m, { side: 'right', text: body }])
        setBody('')
        setLoading(true) // start showing progress

        // add placeholder message for typing effect
        setMessages(m => [...m, { side: 'left', text: '...' }])

        try {
            const res = await axios.post(
                `${API_BASE_URL}/webhook/inbound`,
                payload,
                {
                    headers: {
                        'Content-Type': 'application/json',
                        ...(WEBHOOK_SECRET
                            ? { 'X-Webhook-Secret': WEBHOOK_SECRET }
                            : {})
                    },
                    responseType: 'text'
                }
            )

            rememberNumbers()
            typeWriter(res.data)
        } catch (err) {
            const message =
                err.response
                    ? `Server error ${err.response.status}: ${err.response.data} `
                    : 'Network error          '

            typeWriter(message)
        } finally {
            setLoading(false) // hide progress when done
        }
    }

    function typeWriter(text) {
        let i = 0
        let current = ''

        const id = setInterval(() => {
            current += text[i]
            i++
            setMessages(m => [...m.slice(0, -1), { side: 'left', text: current }])
            if (i >= text.length) clearInterval(id)
        }, 15)
    }

    function handleKeyDown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault() // prevent newline
            sendMessage()
        }
    }

    return (
        <div className="page">
            <div className="phone">
                <div className="phone-screen">
                    <div className="dynamic-island" aria-hidden="true" />

                    <header className="status-bar" aria-hidden="true">
                        <span className="status-time">9:41</span>
                        <span className="status-icons">
                            <svg className="icon-signal" viewBox="0 0 18 12" fill="currentColor">
                                <rect x="0" y="7" width="3" height="5" rx="0.6" />
                                <rect x="5" y="5" width="3" height="7" rx="0.6" />
                                <rect x="10" y="2.5" width="3" height="9.5" rx="0.6" />
                                <rect x="15" y="0" width="3" height="12" rx="0.6" opacity="0.35" />
                            </svg>
                            <svg className="icon-wifi" viewBox="0 0 16 12" fill="currentColor">
                                <path d="M8 9.4a1.35 1.35 0 1 0 0 2.7 1.35 1.35 0 0 0 0-2.7Zm0-3.3c1.2 0 2.3.46 3.15 1.22l-1.1 1.12A2.9 2.9 0 0 0 8 7.6c-.75 0-1.44.28-1.96.74L4.94 7.22A4.35 4.35 0 0 1 8 6.1Zm0-3.15c2.05 0 3.92.78 5.35 2.06L12.2 6.15A5.7 5.7 0 0 0 8 4.55c-1.55 0-2.97.58-4.06 1.54L2.8 4.95A7.85 7.85 0 0 1 8 2.95Z" />
                            </svg>
                            <span className="battery">
                                <span className="battery-body">
                                    <span className="battery-level" />
                                </span>
                                <span className="battery-nub" />
                            </span>
                        </span>
                    </header>

                    <div className="nav-bar">
                        <span className="nav-back" aria-hidden="true">
                            <svg viewBox="0 0 12 20" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M10 2 2 10l8 8" />
                            </svg>
                        </span>
                        <div className="nav-contact">
                            <div className="avatar" aria-hidden="true">{initialsFromNumber(to)}</div>
                            {/* datalist rather than a select: it keeps these
                                exact inputs, so the nav bar keeps its size,
                                and typing an unlisted number is still just
                                typing. */}
                            <label className="contact-name">
                                <span className="sr-only">Receiver</span>
                                <input
                                    value={to}
                                    onChange={e => setTo(e.target.value)}
                                    aria-label="Receiver"
                                    list="recent-to"
                                />
                                <datalist id="recent-to">
                                    {recentTo.map(number => (
                                        <option key={number} value={number} />
                                    ))}
                                </datalist>
                            </label>
                            <label className="contact-from">
                                <span>From</span>
                                <input
                                    value={from}
                                    onChange={e => setFrom(e.target.value)}
                                    aria-label="Sender"
                                    list="recent-from"
                                />
                                <datalist id="recent-from">
                                    {recentFrom.map(number => (
                                        <option key={number} value={number} />
                                    ))}
                                </datalist>
                            </label>
                        </div>
                        <span className="nav-info" aria-hidden="true">
                            <svg viewBox="0 0 24 24" fill="currentColor">
                                <circle cx="12" cy="12" r="10" opacity="0.15" />
                                <path d="M12 10.5a1.2 1.2 0 0 1 1.2 1.2v5.1a1.2 1.2 0 1 1-2.4 0v-5.1a1.2 1.2 0 0 1 1.2-1.2Zm0-4.3a1.45 1.45 0 1 1 0 2.9 1.45 1.45 0 0 1 0-2.9Z" />
                            </svg>
                        </span>
                    </div>

                    <div className="container">
                        <div className="chat" ref={chatRef}>
                            {messages.length === 0 && (
                                <div className="empty-state">
                                    <div className="empty-avatar" aria-hidden="true">{initialsFromNumber(to)}</div>
                                    <p className="empty-name">{to}</p>
                                    <p className="empty-caption">Text Message · iPhone</p>
                                </div>
                            )}
                            {messages.map((m, i) => {
                                const prev = messages[i - 1]
                                const next = messages[i + 1]
                                const isFirst = !prev || prev.side !== m.side
                                const isLast = !next || next.side !== m.side
                                const isTyping = m.side === 'left' && m.text === '...'
                                return (
                                    <div
                                        key={i}
                                        className={`row ${m.side} ${isFirst ? 'first' : ''} ${isLast ? 'last' : ''}`}
                                    >
                                        <div className={`bubble ${m.side} ${isLast ? 'tailed' : ''} ${isTyping ? 'typing' : ''}`}>
                                            {isTyping ? (
                                                <span className="typing-dots" aria-hidden="true">
                                                    <span />
                                                    <span />
                                                    <span />
                                                </span>
                                            ) : (
                                                m.text
                                            )}
                                        </div>
                                    </div>
                                )
                            })}
                        </div>

                        <div className="input">
                            <span className="composer-plus" aria-hidden="true">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                                    <circle cx="12" cy="12" r="10" />
                                    <path d="M12 8v8M8 12h8" />
                                </svg>
                            </span>
                            <textarea
                                value={body}
                                onChange={e => setBody(e.target.value)}
                                placeholder="Text Message"
                                onKeyDown={handleKeyDown}
                                rows={1}
                            />
                            <button
                                className={body.trim() ? 'armed' : ''}
                                onClick={sendMessage}
                                disabled={loading}
                                aria-label="Send"
                            >
                                {loading ? (
                                    <span className="send-spinner" />
                                ) : (
                                    <svg viewBox="0 0 24 24" fill="currentColor">
                                        <path d="M12 4.5c.4 0 .75.16 1.02.43l6.05 6.05a1.1 1.1 0 1 1-1.56 1.56L13.1 8.13V18.4a1.1 1.1 0 1 1-2.2 0V8.13L6.49 12.54a1.1 1.1 0 1 1-1.56-1.56l6.05-6.05A1.45 1.45 0 0 1 12 4.5Z" />
                                    </svg>
                                )}
                            </button>
                        </div>
                    </div>

                    <div className="home-indicator" aria-hidden="true" />
                </div>
            </div>
        </div>
    )
}
