import { useState } from 'react'
import axios from 'axios'
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL


export default function App() {
    const [from, setFrom] = useState('+15551234567')
    const [to, setTo] = useState('+15559876543')
    const [body, setBody] = useState('')
    const [messages, setMessages] = useState([])
    const [loading, setLoading] = useState(false) // new state for progress indicator

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
                JSON.stringify(payload),
                {
                    headers: {
                        'Content-Type': 'text/plain'
                    },
                    responseType: 'text'
                }
            )

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
        <div className="container">
            <div className="header">
                Sender: <input value={from} onChange={e => setFrom(e.target.value)} />
                Receiver: <input value={to} onChange={e => setTo(e.target.value)} />
            </div>

            <div className="chat">
                {messages.map((m, i) => (
                    <div key={i} className={`bubble ${m.side}`}>{m.text}</div>
                ))}
            </div>

            <div className="input">
                <textarea
                    value={body}
                    onChange={e => setBody(e.target.value)}
                    placeholder="Type your message..."
                    onKeyDown={handleKeyDown} // handle Enter key
                />
                <button onClick={sendMessage} disabled={loading}>
                    {loading ? '...                     ' : 'Send'} {/* simple 3-dot indicator */}
                </button>
            </div>
        </div>
    )
}
