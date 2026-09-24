import { useCallback, useEffect, useRef, useState } from 'react'
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
// Names live only in this browser. The simulator is unauthenticated, and the
// only endpoint that knows real member names is behind moderator auth.
const STORAGE_KEY_CONTACTS = 'sms-simulator.contacts'

const MAX_RECENT = 10

// A reply may wait on a moderator approving it, so it arrives whenever it
// arrives. Three seconds keeps the handset feeling live inside the five-second
// budget without hammering the API.
const CONVERSATION_POLL_MS = 3000

const conversationHeaders = WEBHOOK_SECRET
    ? { 'X-Webhook-Secret': WEBHOOK_SECRET }
    : {}

// Inbound is what this handset sent, outbound is what the group sent it.
//
// `body` is shown verbatim. An incoming message already reads "Naruto: ..."
// because the sender is part of the SMS the backend composed, so there is
// nothing for the client to prepend -- and nothing on the outgoing side, where
// the words are this handset's own.
function toBubble(message) {
    return {
        id: message.id,
        side: message.direction === 'inbound' ? 'right' : 'left',
        text: message.body,
    }
}

// The continuation point for the next poll: the last row actually seen, both
// halves of it. A `created_at` alone is not enough, because a fan-out writes its
// copies in one transaction and they share a timestamp exactly.
function cursorOf(messages) {
    const last = messages[messages.length - 1]
    if (!last) return null
    return { after_created_at: last.created_at, after_id: last.id }
}

function describeError(err) {
    if (!err.response) return 'Cannot reach the server.'
    const { status, data } = err.response
    const detail = typeof data === 'string' ? data : data?.detail
    return typeof detail === 'string' ? detail : `Server error ${status}`
}

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

function loadContacts() {
    try {
        const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY_CONTACTS))
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
        return Object.fromEntries(
            Object.entries(parsed).filter(
                ([number, name]) => typeof name === 'string' && name.trim() && number
            )
        )
    } catch {
        return {}
    }
}

function storeContacts(contacts) {
    try {
        localStorage.setItem(STORAGE_KEY_CONTACTS, JSON.stringify(contacts))
    } catch {
        // Names are a convenience; ignore quota/permission failures.
    }
}

function initialsFromNumber(value) {
    const digits = String(value).replace(/\D/g, '')
    if (digits.length >= 2) return digits.slice(-2)
    return '•'
}

// A named contact gets letters; an unnamed one keeps the trailing digits, which
// are still enough to tell two numbers apart at a glance.
function contactInitials(contacts, number) {
    const name = contacts[number]?.trim()
    if (!name) return initialsFromNumber(number)
    const letters = name
        .split(/\s+/)
        .slice(0, 2)
        .map(word => word[0])
        .join('')
    return letters.toUpperCase()
}

/**
 * A phone-number input with a dropdown of every number used before.
 *
 * Replaces a `datalist`, which filtered its own options against the text in the
 * input: with a full number typed there, the only option left matching was the
 * one already selected. This owns its list, so all of them stay visible.
 *
 * Options display as "+17777777777 - Josh" but carry only the bare number, so
 * what reaches the webhook is unchanged.
 */
function NumberField({
    variant,
    ariaLabel,
    value,
    onChange,
    recent,
    contacts,
    onRename,
    onForget,
    onCommit,
}) {
    const [open, setOpen] = useState(false)
    const wrapperRef = useRef(null)

    // Close on any click outside. Listening on pointerdown rather than click so
    // the menu is gone before a click lands on the input behind it.
    useEffect(() => {
        if (!open) return
        function onPointerDown(e) {
            if (!wrapperRef.current?.contains(e.target)) setOpen(false)
        }
        document.addEventListener('pointerdown', onPointerDown)
        return () => document.removeEventListener('pointerdown', onPointerDown)
    }, [open])

    const trimmed = value.trim()

    // A committed number is one the user has finished choosing, as opposed to
    // the half-typed values onChange sees on the way there. Anything keyed by
    // the number has to wait for this or it would act on "+1", "+15", "+155"...
    const commit = () => onCommit?.(value)

    return (
        <div className={`number-field ${variant}`} ref={wrapperRef}>
            <input
                value={value}
                onChange={e => onChange(e.target.value)}
                aria-label={ariaLabel}
                onBlur={commit}
                onKeyDown={e => {
                    if (e.key === 'Escape') setOpen(false)
                    if (e.key === 'Enter') commit()
                }}
            />
            {/* Beside the input rather than inside it: the input's value is the
                number that gets sent, so mixing a name into it would mean
                parsing it back out before every request. */}
            {contacts[trimmed] && (
                <span className="number-field-alias">{`- ${contacts[trimmed]}`}</span>
            )}
            <button
                type="button"
                className="number-caret"
                onClick={() => setOpen(o => !o)}
                aria-label={`${ariaLabel}: recent numbers`}
                aria-expanded={open}
            >
                <svg viewBox="0 0 10 6" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 1l4 4 4-4" />
                </svg>
            </button>

            {open && (
                <div className="number-menu">
                    <ul className="number-menu-list" role="listbox" aria-label={ariaLabel}>
                        {recent.length === 0 && (
                            <li className="number-menu-empty">
                                No numbers yet — send a message to add one.
                            </li>
                        )}
                        {recent.map(number => (
                            <li key={number}>
                                <button
                                    type="button"
                                    role="option"
                                    aria-selected={number === value}
                                    className={`number-menu-option ${number === value ? 'selected' : ''}`}
                                    onClick={() => {
                                        onChange(number)
                                        onCommit?.(number)
                                        setOpen(false)
                                    }}
                                >
                                    <span className="number-menu-number">{number}</span>
                                    {contacts[number] && (
                                        <span className="number-menu-name">
                                            {`- ${contacts[number]}`}
                                        </span>
                                    )}
                                </button>
                                {/* A sibling of the option, not a child: a
                                    button inside a button is invalid HTML and
                                    the click would also select the number. */}
                                <button
                                    type="button"
                                    className="number-menu-forget"
                                    onClick={() => onForget(number)}
                                    aria-label={`Remove ${number} from recent numbers`}
                                    title="Remove from list"
                                >
                                    <svg viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
                                        <path d="M1.5 1.5l7 7M8.5 1.5l-7 7" />
                                    </svg>
                                </button>
                            </li>
                        ))}
                    </ul>

                    {recent.length > 1 && (
                        <div className="number-menu-actions">
                            <button type="button" onClick={() => onForget(null)}>
                                Clear all
                            </button>
                        </div>
                    )}

                    {trimmed && (
                        <label className="number-menu-rename">
                            <span className="sr-only">{`Name for ${trimmed}`}</span>
                            <input
                                value={contacts[trimmed] ?? ''}
                                onChange={e => onRename(trimmed, e.target.value)}
                                placeholder={`Name for ${trimmed}`}
                                onKeyDown={e => e.key === 'Escape' && setOpen(false)}
                            />
                        </label>
                    )}
                </div>
            )}
        </div>
    )
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
    const [contacts, setContacts] = useState(loadContacts)
    const [body, setBody] = useState('')
    const [messages, setMessages] = useState([])
    const [loading, setLoading] = useState(false) // new state for progress indicator
    const [notice, setNotice] = useState(null)
    const chatRef = useRef(null)

    // The pair whose conversation is on screen. Not `from`/`to`, which change on
    // every keystroke: keying the fetch off those would mean a request per
    // character, each for a half-typed number.
    const [committed, setCommitted] = useState(() => ({
        from: from.trim(),
        to: to.trim(),
    }))

    // Identifies the newest load. A response for the previous pair must not land
    // in the conversation that replaced it.
    const loadToken = useRef(0)
    const cursor = useRef(null)
    // Polling waits for the first full load: until then there is no cursor, and
    // a poll would race the load it cannot see.
    const settled = useRef(false)

    // Follow the conversation down as it grows.
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

    // From picks the member, To picks the group, and either one changes which
    // conversation this is -- so both reload. Called on a committed number only.
    function commitNumber(field, next) {
        const value = next.trim()
        if (!value) return
        setCommitted(prev => (prev[field] === value ? prev : { ...prev, [field]: value }))
    }

    /**
     * Replace the visible conversation with the server's.
     *
     * The server owns history: the simulator holds no messages of its own beyond
     * the optimistic bubble a send puts up, and that is discarded here rather
     * than matched against whatever row the backend created.
     */
    const loadConversation = useCallback(async (member, group) => {
        const token = ++loadToken.current
        settled.current = false
        cursor.current = null

        if (!member || !group) {
            setMessages([])
            settled.current = true
            return
        }

        try {
            const { data } = await axios.get(
                `${API_BASE_URL}/webhook/conversation`,
                { params: { from: member, to: group }, headers: conversationHeaders }
            )
            if (token !== loadToken.current) return
            setMessages(data.messages.map(toBubble))
            cursor.current = cursorOf(data.messages)
            setNotice(null)
        } catch (err) {
            if (token !== loadToken.current) return
            setMessages([])
            setNotice(describeError(err))
        } finally {
            if (token === loadToken.current) settled.current = true
        }
    }, [])

    // A full reload whenever the pair changes, which is what makes switching From
    // feel like picking up a different handset.
    useEffect(() => {
        void loadConversation(committed.from, committed.to)
    }, [committed, loadConversation])

    useEffect(() => {
        const { from: member, to: group } = committed
        if (!member || !group) return

        async function poll() {
            // A backgrounded tab has nobody watching it.
            if (document.visibilityState === 'hidden') return
            // Wait for the full load: until it lands there is no cursor, and a
            // poll would be racing a request whose result it cannot see.
            if (!settled.current) return

            // Read fresh on every tick rather than captured when the interval
            // was created. A send reloads the conversation, which bumps the
            // token, and a captured one would then never match again -- leaving
            // the handset silent for as long as it stayed on this conversation.
            const generation = loadToken.current
            // Captured, because the branch below has to reflect the cursor this
            // request was actually made with, not whatever it is by the time the
            // response lands.
            const from_ = cursor.current

            try {
                const { data } = await axios.get(
                    `${API_BASE_URL}/webhook/conversation`,
                    {
                        params: { from: member, to: group, ...(from_ ?? {}) },
                        headers: conversationHeaders,
                    }
                )
                // A reload started while this was in flight, so its answer is
                // the current one and this response is history.
                if (generation !== loadToken.current || !data.messages.length) return

                const arriving = data.messages.map(toBubble)
                if (from_) {
                    // Dedupe by server id. Cheap insurance: a retried request or
                    // an overlapping cursor must not double a bubble.
                    setMessages(current => {
                        const seen = new Set(current.map(m => m.id))
                        return [...current, ...arriving.filter(m => !seen.has(m.id))]
                    })
                } else {
                    // No cursor means the conversation was empty at load, so
                    // this response is the whole of it.
                    setMessages(arriving)
                }
                cursor.current = cursorOf(data.messages) ?? cursor.current
            } catch {
                // A failed poll is not worth a banner: the next one is three
                // seconds away, and a transient blip would flash and vanish.
            }
        }

        const timer = setInterval(() => void poll(), CONVERSATION_POLL_MS)
        return () => clearInterval(timer)
    }, [committed])

    // An empty name is a removal, not a contact called "": otherwise clearing
    // the field would leave a blank dash in the dropdown.
    function renameContact(number, name) {
        setContacts(prev => {
            const next = { ...prev }
            if (name.trim()) next[number] = name
            else delete next[number]
            storeContacts(next)
            return next
        })
    }

    // A null number clears the whole list. Names are deliberately kept: the
    // number stays in the field and comes back on the next send, and retyping a
    // name you already set would be busywork.
    function forgetNumber(key, setter, number) {
        setter(prev => {
            const next = number === null ? [] : prev.filter(v => v !== number)
            storeNumbers(key, next)
            return next
        })
    }

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
        const text = body.trim()
        if (!text) return

        // Typing a number and hitting Send without leaving the field never fires
        // a blur, so commit here too or the message would go to one pair while
        // the screen shows another.
        const member = from.trim()
        const group = to.trim()
        commitNumber('from', member)
        commitNumber('to', group)

        setBody('')
        setLoading(true)
        // Optimistic, so the handset responds to the keypress. Discarded by the
        // reload below rather than reconciled: which row the backend wrote is the
        // server's business, and guessing at it is how phantom bubbles happen.
        setMessages(m => [...m, { id: `pending-${Date.now()}`, side: 'right', text }])

        try {
            await axios.post(
                `${API_BASE_URL}/webhook/inbound`,
                { from: member, to: group, body: text },
                { headers: { 'Content-Type': 'application/json', ...conversationHeaders } }
            )
            rememberNumbers()
            setNotice(null)
        } catch (err) {
            setNotice(describeError(err))
        } finally {
            setLoading(false)
        }

        // The authoritative reconciliation point, run whether the post succeeded
        // or not: on success it brings back the stored row plus anything routing
        // produced, and on failure it drops an optimistic bubble for a message
        // that was never recorded.
        await loadConversation(member, group)
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
                            <div className="avatar" aria-hidden="true">{contactInitials(contacts, to)}</div>
                            <div className="contact-name">
                                <NumberField
                                    variant="to"
                                    ariaLabel="Receiver"
                                    value={to}
                                    onChange={setTo}
                                    recent={recentTo}
                                    contacts={contacts}
                                    onRename={renameContact}
                                    onForget={number =>
                                        forgetNumber(STORAGE_KEY_RECENT_TO, setRecentTo, number)
                                    }
                                    onCommit={value => commitNumber('to', value)}
                                />
                            </div>
                            <div className="contact-from">
                                <span>From</span>
                                <NumberField
                                    variant="from"
                                    ariaLabel="Sender"
                                    value={from}
                                    onChange={setFrom}
                                    recent={recentFrom}
                                    contacts={contacts}
                                    onRename={renameContact}
                                    onForget={number =>
                                        forgetNumber(STORAGE_KEY_RECENT_FROM, setRecentFrom, number)
                                    }
                                    onCommit={value => commitNumber('from', value)}
                                />
                            </div>
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
                                    <div className="empty-avatar" aria-hidden="true">{contactInitials(contacts, to)}</div>
                                    <p className="empty-name">{contacts[to.trim()] || to}</p>
                                    <p className="empty-caption">Text Message · iPhone</p>
                                </div>
                            )}
                            {messages.map((m, i) => {
                                const prev = messages[i - 1]
                                const next = messages[i + 1]
                                const isFirst = !prev || prev.side !== m.side
                                const isLast = !next || next.side !== m.side
                                return (
                                    // Keyed by the server's id, so React remounts
                                    // only genuinely new rows -- which is what
                                    // makes the arrival animation mean anything.
                                    <div
                                        key={m.id}
                                        className={`row ${m.side} ${isFirst ? 'first' : ''} ${isLast ? 'last' : ''}`}
                                    >
                                        <div className={`bubble ${m.side} ${isLast ? 'tailed' : ''}`}>
                                            {m.text}
                                        </div>
                                    </div>
                                )
                            })}
                            {notice && <p className="chat-notice">{notice}</p>}
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
