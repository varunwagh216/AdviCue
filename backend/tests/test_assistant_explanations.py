from unittest.mock import patch
import pytest
from app.ai.local_models import LocalModelError
from tests.test_offline_search import headers

@pytest.mark.parametrize('query',[
    'What is a SIP?', 'Explain diversification', 'How does inflation affect savings?',
    'Compare time-weighted and money-weighted returns', 'How do I import data?',
    'What does pattern detection do?', 'Draft a meeting agenda',
    'Why is valuation coverage important?', 'Explain Python lists',
])
def test_explanations_do_not_become_portfolio_search(client,query):
    h=headers(client)
    with patch('app.services.assistant_answers.local_llm_json',return_value={'answer':'A direct explanation.'}) as llm:
        r=client.post('/api/v1/assistant/search',json={'query':query},headers=h)
    assert r.status_code==200
    assert r.json()['intent']=='EXPLANATION' and r.json()['items']==[]
    if llm.called:
        assert llm.call_args.args[1]['question']==query
        assert 'Test Investor' not in str(llm.call_args)
    else:
        assert r.json()['mode']=='LOCAL_REFERENCE'

def test_model_unavailable_does_not_return_unrelated_records(client):
    h=headers(client)
    with patch('app.services.assistant_answers.local_llm_json',side_effect=LocalModelError('offline')):
        r=client.post('/api/v1/assistant/search',json={'query':'Explain diversification'},headers=h)
    assert r.json()['mode']=='AI_UNAVAILABLE' and not r.json()['items']

def test_live_quotes_do_not_call_model(client):
    h=headers(client)
    with patch('app.services.assistant_answers.local_llm_json') as llm:
        r=client.post('/api/v1/assistant/search',json={'query':'What is the current Nifty price?'},headers=h)
    llm.assert_not_called()
    assert r.json()['mode']=='OFFLINE_LIMIT'

def test_named_client_stays_in_scoped_records(client):
    h=headers(client)
    with patch('app.api.workspace.local_llm_json',return_value={'intent':'CLIENT','client_search':''}), patch('app.services.assistant_answers.local_llm_json') as llm:
        r=client.post('/api/v1/assistant/search',json={'query':'Where does Test Investor A stand?'},headers=h)
    llm.assert_not_called()
    assert r.json()['items'][0]['client_name']=='Test Investor A'
    assert 'Test Investor B' not in r.text


def test_sip_definition_is_grounded_offline(client):
    h=headers(client)
    with patch('app.services.assistant_answers.local_llm_json') as llm:
        data=client.post('/api/v1/assistant/search',json={'query':'What is a SIP?'},headers=h).json()
    llm.assert_not_called()
    assert 'Systematic Investment Plan' in data['answer']
    assert 'amfiindia.com' in data['note']
