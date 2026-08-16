# Create a sequence to capture user info

from openai import OpenAI

client = OpenAI()

conversation = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": "Hi, I want to register."},
]

response = client.chat.completions.create(model="gpt-5-mini", messages=conversation)

print(response.choices[0].message.content)

def capture_info():
    print('capture info')
