from types import SimpleNamespace
from app.api import local_ai


def test_runtime_health_distinguishes_ready_loading_and_missing(monkeypatch):
    import httpx
    monkeypatch.setattr(local_ai,'local_llama_cpp_url',lambda:'http://127.0.0.1:8080')
    state={'code':200}
    class Client:
        def __init__(self,**kwargs):
            assert kwargs['trust_env'] is False
            assert kwargs['follow_redirects'] is False
            assert kwargs['timeout']==2
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,url):
            assert url=='http://127.0.0.1:8080/health'
            if state['code']==0:raise httpx.ConnectError('Unavailable')
            return SimpleNamespace(status_code=state['code'])
    monkeypatch.setattr(httpx,'Client',Client)
    for code,expected in [(200,'READY'),(503,'STARTING'),(0,'NEEDS_SETUP'),(404,'NEEDS_SETUP')]:
        state['code']=code
        assert local_ai.ai_status(user=SimpleNamespace())['runtime_state']==expected
