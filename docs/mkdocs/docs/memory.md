Memory

Per session, when an original prompt is received, we create a session based on the requester's phone number (i.e. from) and the destination number (i.e. to)
A session can last max two days.
A session can manually terminated by moderator
A session can automatically terminated by the agent
Store summary


Separating memory by user_id:



session_memories = [{"session_id": 10001, "user_id":9, "chat_history":"..." }, {"session_id": 10001, "user_id":7, "chat_history":"..." }]

if session_id not in session_memories:
    user_memories[user_id] = ConversationBufferMemory(memory_key="chat_history")

memory = user_memories[user_id]

How long does ChatGPT store my previous prompts?