import json
import requests
from config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL


def llm_available() -> bool:
    return bool(LLM_BASE_URL and LLM_API_KEY and LLM_MODEL)


def chat_json(system_prompt: str, user_prompt: str) -> dict:
    """
    Small OpenAI-compatible adapter.
    If no LLM is configured, callers should use deterministic fallbacks.
    """
    if not llm_available():
        return {}

    url = f"{LLM_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)
