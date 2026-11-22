"""Offline panel regressions. All writes use temporary SQLite fixtures."""
import json

import pytest


@pytest.fixture
def panel(tmp_path, monkeypatch):
    from webui import db
    db.close_connections()
    monkeypatch.setattr(db, 'DB_PATH', tmp_path / 'panel.db')
    db.init_db()
    from fastapi.testclient import TestClient
    from webui.app import app
    with TestClient(app) as client:
        yield db, client
    db.close_connections()


def add_mail(db):
    db.import_accounts('person@example.com----https://mail.example/fixture-private-link', kind='icloud_relay')


def test_accounts_list_does_not_expose_credentials(panel):
    db, client = panel
    add_mail(db)
    row = client.get('/api/accounts').json()['items'][0]
    assert row['email'] == 'person@example.com'
    assert not {'password', 'client_id', 'refresh_token', 'relay_url'} & row.keys()
    assert 'fixture-private-link' not in json.dumps(row)
    assert db.get_account(row['email'])['relay_url'].endswith('fixture-private-link')


def test_import_updates_password_and_client_id(panel):
    db, _ = panel
    def line(password, client):
        return f'person@outlook.com----{password}----{client}----fixture-refresh-long-enough-for-validation'
    db.import_accounts(line('old-password', 'old-client'), kind='outlook')
    result = db.import_accounts(line('new-password', 'new-client'), kind='outlook')
    assert result['updated'] == 1
    row = db.get_account('person@outlook.com')
    assert row['password'] == 'new-password'
    assert row['client_id'] == 'new-client'


@pytest.mark.parametrize('state', ['in_use', 'done'])
def test_import_does_not_requeue_active_or_done_mail(panel, state):
    db, _ = panel
    add_mail(db)
    db.claim_account('person@example.com')
    if state == 'done':
        db.mark_done('person@example.com')
    before = db.get_account('person@example.com')
    result = db.import_accounts('person@example.com----https://mail.example/updated-fixture', kind='icloud_relay')
    assert result['updated'] == 1
    after = db.get_account('person@example.com')
    assert after['status'] == state
    assert after['claimed_at'] == before['claimed_at']
    assert after['finished_at'] == before['finished_at']


def test_live_filters_read_only_live_check_status(panel):
    db, _ = panel
    db.save_registered({'email': 'unrelated@example.com', 'diagnostic': {'status': 'live'}, 'note': 'token_invalid'})
    db.save_registered({'email': 'live@example.com'})
    db.update_live_check('live@example.com', {'status': 'live', 'label': 'live'})
    db.save_registered({'email': 'invalid@example.com'})
    db.update_live_check('invalid@example.com', {'status': 'token_invalid', 'label': 'invalid'})
    assert [r['email'] for r in db.list_registered(filter_rt='live')] == ['live@example.com']
    assert [r['email'] for r in db.list_registered(filter_rt='token_invalid')] == ['invalid@example.com']
    assert db.count_registered('unchecked') == 1


def test_empty_invite_selection_is_not_global_reset(panel):
    db, client = panel
    db.import_invite_codes('FIXTURE-CODE', max_uses=2)
    db._conn().execute("UPDATE invite_codes SET status='invalid'")
    db._conn().commit()
    response = client.post('/api/invites/reset', json={'codes': []})
    assert response.status_code == 200
    assert response.json()['reset'] == 0
    assert db.list_invite_codes()[0]['status'] == 'invalid'
    # Omitting the selector is the explicit repair-all operation used by the API.
    assert client.post('/api/invites/reset', json={}).json()['reset'] == 1


@pytest.mark.parametrize('url', [
    '/api/accounts?limit=-1', '/api/accounts?offset=-1',
    '/api/registered?limit=0', '/api/invites?limit=10001', '/api/runs?limit=-1',
])
def test_invalid_pagination_rejected(panel, url):
    _, client = panel
    assert client.get(url).status_code == 422


def test_negative_stale_age_does_not_release_active_mail(panel):
    db, client = panel
    add_mail(db)
    db.claim_account('person@example.com')
    assert client.post('/api/accounts/release_stale?stale_seconds=-1').status_code == 422
    assert db.get_account('person@example.com')['status'] == 'in_use'


def test_changed_failed_mail_can_be_retried(panel):
    db, _ = panel
    add_mail(db)
    db.claim_account('person@example.com')
    db.mark_failed('person@example.com', 'fixture failure')
    db.import_accounts('person@example.com----https://mail.example/replacement', kind='icloud_relay')
    row = db.get_account('person@example.com')
    assert row['status'] == 'available'
    assert row['claimed_at'] is None
    assert row['finished_at'] is None
    assert row['fail_reason'] is None


def test_filters_tolerate_legacy_invalid_json(panel):
    db, client = panel
    db.save_registered({'email': 'legacy@example.com'})
    db._conn().execute("UPDATE registered SET extra_json=?", ('legacy non-json fixture',))
    db._conn().commit()
    for status, expected in [('live', 0), ('token_invalid', 0), ('unchecked', 1)]:
        response = client.get('/api/registered', params={'filter': status})
        assert response.status_code == 200
        assert response.json()['total'] == expected


def test_normal_pagination_still_works(panel):
    db, client = panel
    add_mail(db)
    response = client.get('/api/accounts?limit=1&offset=1')
    assert response.status_code == 200
    assert response.json()['total'] == 1
    assert response.json()['items'] == []
