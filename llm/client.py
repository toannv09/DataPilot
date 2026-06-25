"""OpenAI API client với retry logic và cache."""

import os
import time

from openai import APIStatusError, OpenAI

from llm.cache import get_cached, set_cached

MODEL_70B = "gpt-5.4-nano"
MODEL_8B = "gpt-5.4-nano"

MAX_RETRIES = 3

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    return _client


def call_llm(prompt, system=None, model=MODEL_70B, use_cache=True):
    """Gọi OpenAI API, retry tối đa 3 lần khi rate limit, cache theo hash(input)."""
    cache_key = {"prompt": prompt, "system": system, "model": model}
    if use_cache:
        cached = get_cached(cache_key)
        if cached is not None:
            return cached

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    client = _get_client()

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(model=model, messages=messages)
            content = response.choices[0].message.content

            try:
                from mlops.tracker import log_tokens
                log_tokens(response.usage.total_tokens, model)
            except Exception:
                pass

            if use_cache:
                set_cached(cache_key, content)

            return content
        except APIStatusError as e:
            last_error = e
            if e.status_code == 429:
                time.sleep(2 ** attempt)
            else:
                raise
        except Exception as e:
            last_error = e
            time.sleep(2 ** attempt)

    raise RuntimeError(f"OpenAI API call thất bại sau {MAX_RETRIES} lần thử: {last_error}")
