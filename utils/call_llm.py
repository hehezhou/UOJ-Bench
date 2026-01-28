import requests
import json
import os
import openai

__all__ = ['call_llm_details', 'call_llm_full', 'call_llm']

def generate_messages(message):
    if isinstance(message, str):
        return [
            {
                "role": "user",
                "content": message
            }
        ]
    return message

def call_api(message, model, url, api_key):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,  # You can change the model
        "messages": generate_messages(message)
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()  # Raise exception for error status codes
    return response.json()

openrouter_api_key = os.environ.get('OPENROUTER_KEY')
openrouter_url = "https://openrouter.ai/api/v1/chat/completions"
def call_openrouter(message, model="openai/gpt-oss-120b"):
    return call_api(message, model, openrouter_url, openrouter_api_key)

def call_llm_full(message, m):
    if m == "gpt-oss-120b":
        return call_openrouter(message, "openai/" + m)
    else:
        raise Exception("unsupported model")

def call_llm(message, m):
    result = call_llm_full(message, m)['choices'][0]['message']
    return str(result['content'])

def call_llm_details(message, m):
    llm = call_llm_full(message, m)
    result = llm['choices'][0]['message']
    return str(result['content']), result, llm.get('usage', {})