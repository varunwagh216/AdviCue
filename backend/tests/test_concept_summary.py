from tests.conftest import sign_in
from tests.test_phase34 import seed_test_group

def test_chart_summary_enforces_client_scope(client):
    seed_test_group()
    sign_in(client)
    result=client.get('/api/v1/workspace-summary')
    assert result.status_code==200,result.text
    summary=result.json()
    own={i['id'] for i in client.get('/api/v1/investors').json()['items']}
    assert {i['id'] for i in summary['clients']}==own
    assert sum(summary['risk_counts'].values())==len(own)
    assert 'PAT-1' not in {i['id'] for i in summary['clients']}
    assert 'PAT-3' not in {i['id'] for i in summary['clients']}
    assert float(summary['recorded_holdings_total'])==3000

def test_chart_summary_requires_login(client):
    assert client.get('/api/v1/workspace-summary').status_code==401
