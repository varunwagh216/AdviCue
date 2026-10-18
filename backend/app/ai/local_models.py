"""Local llama.cpp 1B GGUF inference and offline whisper.cpp transcription.

Only loopback HTTP is allowed; generated text is always untrusted and validated
by the API layer before storing any financial brief or meeting extraction.
"""
from __future__ import annotations
import json
from ipaddress import ip_address
from urllib.parse import urlparse

import httpx
from app.core.config import settings


class LocalModelError(Exception):
    pass


def local_llama_cpp_url() -> str:
    """Reject remote, credential-bearing, redirected and non-HTTP AI endpoints."""
    url = settings.llama_cpp_url.rstrip('/')
    parsed = urlparse(url)
    hostname = parsed.hostname or ''
    try:
        is_local = ip_address(hostname).is_loopback
    except ValueError:
        is_local = hostname.lower() == 'localhost'
    if (parsed.scheme != 'http' or not is_local or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ('', '/')
            or parsed.port is None):
        raise LocalModelError('LLAMA_CPP_URL must be a local HTTP address such as http://127.0.0.1:8080')
    return url


def local_llm_json(system: str, facts: dict, *, max_response_chars: int = 5000, response_schema: dict | None = None) -> dict:
    """Use portable llama-server OpenAI-compatible JSON output; no hosted APIs."""
    url = local_llama_cpp_url() + '/v1/chat/completions'
    # Classification has a bounded two-field response. Give prose/extraction
    # their existing generous budget; never truncate financial evidence inputs.
    properties = (response_schema or {}).get('properties', {})
    is_router = set(properties) == {'intent', 'client_search'}
    token_budget = 512 if is_router else (1400 if response_schema else 750)
    # Compact serialization preserves every value while avoiding whitespace
    # tokens in long portfolio facts and meeting contexts.
    context = json.dumps(facts, ensure_ascii=False, separators=(',', ':'))
    try:
        response = httpx.post(
            url,
            json={
                'model': settings.llama_cpp_model,
                'messages': [
                    {'role': 'system', 'content': system + ' Return ONLY a valid JSON object.'},
                    {'role': 'user', 'content': context},
                ],
                'response_format': {'type': 'json_object', **({'schema':response_schema} if response_schema else {})},
                'stream': False,
                'temperature': 0,
                'max_tokens': token_budget,
                'seed': 42,
                # Each client may have a different provenance enum/schema.
                # Avoid reusing a prefix/grammar state between client requests.
                'cache_prompt': False,
            },
            timeout=httpx.Timeout(60.0 if is_router else 180.0, connect=3.0), trust_env=False,
            follow_redirects=False,
        )
        response.raise_for_status()
        choices = response.json().get('choices', [])
        if choices and isinstance(choices[0], dict) and choices[0].get('finish_reason') == 'length':
            raise LocalModelError('Local model reached its response limit; no partial answer was accepted')
        payload = choices[0]['message']['content'] if choices else None
        if not isinstance(payload, str) or not payload.strip() or len(payload) > max_response_chars:
            raise LocalModelError('Local llama.cpp returned empty or oversized output')
        result = json.loads(payload)
        if not isinstance(result, dict):
            raise LocalModelError('Local llama.cpp did not return a JSON object')
        return result
    except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError) as exc:
        raise LocalModelError('Portable llama.cpp is unavailable or returned invalid JSON. '
                              'Run RUN_WINDOWS.bat and check local-ai-logs/llama-server.stderr.log.') from exc


def transcribe_audio_locally(audio: bytes, suffix: str) -> str:
    from app.ai.speech import transcribe
    return transcribe(audio, suffix)
