⸻

🔁 Message Flow (High-Level)
 1. Message Sent
   • A user sends a text message to the system.
 2. AI Interpretation
   • The server analyzes the message to determine:
   • Intent (e.g., request, offer, announcement)
   • Constraints (location, availability, relevance)
   • Context (past interactions, opt-in signals)
 3. Moderator Review
   • The system sends a summary to a human moderator:
   • Who sent the message
   • Interpreted intent and need
   • Suggested recipient list (with reasoning)
 4. Recipient Confirmation
   • The moderator can:
   • Approve the suggested recipients
   • Modify the list
   • Expand or restrict delivery
 5. Message Delivery
   • Messages are sent to confirmed recipients only.
 6. Recipient Responses
   • Recipients reply to the server (not directly to the sender).
 7. AI Summarization
   • Responses are analyzed and summarized.
 8. Moderator Decision (Optional)
   • The moderator receives a summary and can:
   • Take further action
   • Share updates
   • Close the loop

This human-in-the-loop design ensures accountability, trust, and social safety.




workflow manager
conversation manager
AI agent, 
  User message
     │
     ▼
┌─────────────────────────┐
│ Small AI model          │
│ Intent + Entity Parser  │
└────────────┬────────────┘
             │
             ▼
      Structured request
             │
             ▼
┌─────────────────────────┐
│ Embedding model         │  ← AI, but NOT generative AI
└────────────┬────────────┘
             │
             ▼
      Vector similarity
             │
             ▼
┌─────────────────────────┐
│ TextRoute Core Logic    │  ← YOUR custom logic
│                         │
│ • filters               │
│ • constraints           │
│ • distance              │
│ • availability          │
│ • relevance             │
│ • provider attributes   │
│ • scoring               │
└────────────┬────────────┘
             │
             ▼
       Ranked candidates
             │
             ▼
┌─────────────────────────┐
│ Generative LLM          │  ← limited involvement
│                         │
│ Turn results into       │
│ natural conversation    │
└─────────────────────────┘

routing service
clean interfaces