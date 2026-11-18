"""WebUI 后端、邮箱 OTP 解析、邀请码裂变与导出全链路冒烟测试（使用临时数据库，零污染真实 webui.db）。"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def test_mail_provider_otp_formats():
    from mail_providers.icloud_relay import parse_relay_html

    # 1) muse-protocol 标准 OTP JSON 源
    feed_json = json.dumps([
        {"otp": "111111", "time": "2026-11-16T10:00:00Z"},
        {"otp": "882910", "time": "2026-11-16T10:05:00Z"},
    ])
    msgs = parse_relay_html(feed_json)
    assert len(msgs) == 2 and msgs[0]["otp"] == "882910" and msgs[0]["strict_utc"] is True, msgs

    # 2) 本地 4173 iCloud 工作台：空收件箱不得误走 fallback
    empty_4173 = json.dumps({"email": "test@icloud.com", "message": None})
    assert parse_relay_html(empty_4173) == []

    # 3) 本地 4173：若最新一封是旧 OpenAI 邮件，应严格忽略，防止共用邮箱串码
    openai_4173 = json.dumps({
        "email": "test@icloud.com",
        "message": {
            "id": "m-old",
            "subject": "Your ChatGPT code is 999999",
            "sender": "noreply@tm.openai.com",
            "code": "999999",
            "bodyText": "Your OpenAI verification code is 999999",
            "receivedAt": "2026-11-16T11:00:00.000Z",
        },
    })
    assert parse_relay_html(openai_4173) == []

    # 4) 本地 4173：收到 Muse / Meta 验证码邮件，准确提取
    muse_4173 = json.dumps({
        "email": "test@icloud.com",
        "message": {
            "id": "m-muse-1",
            "subject": "Muse 確認コード",
            "sender": "noreply_at_muse_ai_abc@icloud.com",
            "code": "654321",
            "bodyText": "Muse の認証コードは 654321 です。",
            "receivedAt": "2026-11-16T12:00:00.000Z",
        },
    })
    msgs_muse = parse_relay_html(muse_4173)
    assert len(msgs_muse) == 1 and msgs_muse[0]["otp"] == "654321", msgs_muse
    print("[PASS] mail_provider_otp_formats")


def test_db_and_fastapi_routes():
    with tempfile.TemporaryDirectory() as tmp:
        from webui import db
        orig_db = db.DB_PATH
        try:
            db.DB_PATH = Path(tmp) / "test_webui.db"
            db._invite_inflight.clear()
            db.init_db()

            from fastapi.testclient import TestClient
            from webui.app import app

            client = TestClient(app)

            # 1) 静态首页 + 健康检查
            r_root = client.get("/")
            assert r_root.status_code == 200 and "Muse Register" in r_root.text
            r_health = client.get("/api/health")
            assert r_health.status_code == 200 and r_health.json()["ok"] is True

            # Proxy settings persist in the server-side database and are deduplicated.
            r_proxy_default = client.get("/api/settings/proxy")
            assert r_proxy_default.status_code == 200
            assert r_proxy_default.json()["configured"] is False
            r_proxy_save = client.post("/api/settings/proxy", json={
                "proxies": ["jp.example:8000:user:pass", "jp.example:8000:user:pass", "# note"],
            })
            assert r_proxy_save.status_code == 200 and r_proxy_save.json()["count"] == 1
            assert client.get("/api/settings/proxy").json()["proxies"] == ["jp.example:8000:user:pass"]

            # 2) 导入邮箱（2段格式）
            r_imp = client.post("/api/import", json={
                "kind": "icloud_relay",
                "text": "u1@icloud.com----http://127.0.0.1:4173/openapi/mail/u1%40icloud.com/tok1/latest\n"
                        "u2@icloud.com----https://otp.example/u2",
            })
            assert r_imp.status_code == 200 and r_imp.json()["inserted"] == 2

            # 3) 导入种子邀请码 + 并发领用与用满逻辑
            r_inv = client.post("/api/invites/import", json={"text": "SEED-CODE-01", "max_uses": 2})
            assert r_inv.status_code == 200 and r_inv.json()["inserted"] == 1
            assert r_inv.json()["stats"]["remaining_uses"] == 2

            c1 = db.claim_invite_code()
            c2 = db.claim_invite_code()
            c3 = db.claim_invite_code()
            assert c1 == "SEED-CODE-01" and c2 == "SEED-CODE-01" and c3 is None
            db.finish_invite_code("SEED-CODE-01", True, "redeemed")
            db.finish_invite_code("SEED-CODE-01", True, "redeemed")
            st = db.invite_stats()
            assert st["exhausted"] == 1 and st["remaining_uses"] == 0, st

            # 4) 注册结果入库与导出格式校验
            db.save_registered({
                "email": "u1@icloud.com",
                "account_id": "frl-998877",
                "access_token": "frl_tok_xxx",
                "session_token": "hatch_sess_cookie_value_886chars",
                "refresh_token": "refresh_fixture_value",
                "id_token": "id_fixture_value",
                "csrf_token": "csrf_fixture_value",
                "status": "redeemed",
                "stage": "own_code",
                "own_code": "NEW-MUSE-CODE",
                "used_invite_code": "SEED-CODE-01",
                "ip": "203.0.113.88",
                "first_name": "ハルト",
                "last_name": "佐藤",
                "date_of_birth": "1994-05-12",
            })

            r_reg = client.get("/api/registered?filter=has_own_code")
            assert r_reg.status_code == 200 and r_reg.json()["total"] == 1
            item = r_reg.json()["items"][0]
            assert item["own_code"] == "NEW-MUSE-CODE" and item["st_len"] > 10
            assert item["token_count"] == 5
            assert not {"access_token", "session_token", "refresh_token", "id_token", "csrf_token"}.intersection(item)
            serialized_item = json.dumps(item)
            for secret_fixture in ("frl_tok_xxx", "hatch_sess_cookie_value_886chars", "refresh_fixture_value", "id_fixture_value", "csrf_fixture_value"):
                assert secret_fixture not in serialized_item

            r_exp = client.post("/api/registered/export", json={"format": "own_codes", "all": True})
            assert r_exp.status_code == 200 and r_exp.json()["text"] == "NEW-MUSE-CODE"

            r_exp_full = client.post("/api/registered/export", json={"format": "full_relay", "all": True})
            assert "u1@icloud.com----hatch_sess_cookie_value_886chars----NEW-MUSE-CODE----http://127.0.0.1:4173" in r_exp_full.json()["text"]

            r_exp_json = client.post("/api/registered/export", json={"format": "json_all", "all": True})
            assert r_exp_json.status_code == 200 and r_exp_json.json()["mode"] == "download"
            print("[PASS] db_and_fastapi_routes")
        finally:
            db.close_connections()
            db.DB_PATH = orig_db
            db._invite_inflight.clear()


def test_muse_flow_end_to_end_mock():
    from auth_flow import MuseFlow, MuseFlowError

    class DummyMail:
        display_name = "Dummy"
        def create_mailbox(self):
            return "test_muse@icloud.com"
        def wait_for_otp(self, email_addr, timeout=45, issued_after=None):
            return "612890"

    class MockMuseClient:
        def __init__(self, proxy=None, impersonate="chrome142", lang="ja", timeout=30):
            self.fp = impersonate
            self.lang = lang
            self.s = None
            self.tos_content_version = None
            self._waitlist = False

        def open_home(self): pass
        def restart(self, resume=False): return "csrf_mock_123"
        def send_otp(self, email): return {}
        def confirm_otp(self, code):
            assert code == "612890"
            self.tos_content_version = "ntm_dynamic_v4"
            return {"registration_state": "completion_required", "tos": {"content_version": "ntm_dynamic_v4"}}
        def register_completion(self, dob, first, last, remember_device=True):
            return {"auth_meta_session": {"frl_access_token": "frl_at_mock", "frl_account_id": "uid_mock_88"}}
        def session_cookie(self, name="hatch_sess"):
            return "hatch_sess_mock_value"
        def activate_session(self, token):
            return {
                "state": "disclosure",
                "disclosure_text": "動的同意文",
                "disclosure_version": "HATCH_ROW_v0",
                "resolved_destination": "main_app",
                "source_url": "https://muse.ai/",
            }
        def accept_tos(self, onboarding=None): pass
        def wake_vm(self): return "11111111-2222-3333-4444-555555555555"
        def stateful_sharing(self): pass
        def is_live(self): return True
        def redeem(self, code): return True, "redeemed"
        def scratch_code(self): return "HARVESTED-CODE-99"
        def close(self): pass

    harvested = []
    early_saved = []
    with patch("auth_flow.MuseClient", MockMuseClient), patch("auth_flow.resolve_exit_ip", return_value="133.242.10.20"):
        flow = MuseFlow(
            proxy="jp.example:8000:u:p",
            redeem_mode="pool",
            on_early_save=lambda r: early_saved.append(r.account_id),
            claim_pool_code=lambda: "POOL-SEED-1",
            finish_pool_code=lambda c, ok, r: None,
            on_own_code=lambda own, em: harvested.append((own, em)),
        )
        res = flow.run_register(DummyMail())
        assert res.status == "redeemed"
        assert res.account_id == "uid_mock_88"
        assert res.own_code == "HARVESTED-CODE-99"
        assert res.ip == "133.242.10.20"
        assert early_saved == ["uid_mock_88"]
        assert harvested == [("HARVESTED-CODE-99", "test_muse@icloud.com")]
    print("[PASS] muse_flow_end_to_end_mock")


def main():
    test_mail_provider_otp_formats()
    test_db_and_fastapi_routes()
    test_muse_flow_end_to_end_mock()
    print("WebUI 全链路冒烟通过 3/3")


if __name__ == "__main__":
    main()
