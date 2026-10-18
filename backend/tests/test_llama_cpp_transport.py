"""Portable llama.cpp transport; no real network or models needed."""
from dataclasses import replace
from unittest.mock import patch
import httpx
import pytest
from app.ai.local_models import LocalModelError, local_llama_cpp_url, local_llm_json
from app.core.config import settings


def test_local_model_url_rejects_cloud_and_network_endpoints():
    for url in ('https://api.example.com', 'http://192.168.0.5:8080',
                'http://127.0.0.1:8080/evil', 'http://example.com:8080',
                'http://user:pass@localhost:8080'):
        with patch('app.ai.local_models.settings', replace(settings, llama_cpp_url=url)):
            with pytest.raises(LocalModelError):
                local_llama_cpp_url()
    assert local_llama_cpp_url() == 'http://127.0.0.1:8080'


def test_llama_cpp_uses_local_json_chat_endpoint_and_rejects_redirects():
    def fake_post(url, *, json, **kwargs):
        assert url == 'http://127.0.0.1:8080/v1/chat/completions'
        assert json['model'] == settings.llama_cpp_model
        assert json['response_format'] == {'type': 'json_object'}
        assert json['stream'] is False
        assert json['messages'][0]['role'] == 'system'
        assert json['messages'][1]['role'] == 'user'
        assert kwargs['trust_env'] is False
        assert kwargs['follow_redirects'] is False
        return httpx.Response(200, json={'choices':[{'message':{'content':'{"summary":"source-grounded"}'}}]}, request=httpx.Request('POST',url))
    with patch('app.ai.local_models.httpx.post', side_effect=fake_post):
        assert local_llm_json('Return JSON.', {'investor_id':'INV0009'}) == {'summary':'source-grounded'}


def test_llama_cpp_rejects_bad_response_and_server_failures():
    def server_output(content):
        url='http://127.0.0.1:8080/v1/chat/completions'
        return httpx.Response(200, json={'choices':[{'message':{'content':content}}]}, request=httpx.Request('POST',url))
    with patch('app.ai.local_models.httpx.post', return_value=server_output('not json')):
        with pytest.raises(LocalModelError): local_llm_json('sys', {})
    with patch('app.ai.local_models.httpx.post', return_value=server_output('{"a":2}'*1000)):
        with pytest.raises(LocalModelError): local_llm_json('sys', {})
    with patch('app.ai.local_models.httpx.post', side_effect=httpx.ConnectError('offline')):
        with pytest.raises(LocalModelError): local_llm_json('sys', {})
