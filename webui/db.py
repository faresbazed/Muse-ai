"""SQLite 数据存储层（邮箱号池 + 邀请码池 + Muse 注册结果 + 运行记录 + 全局配置）。"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

DB_PATH = Path(__file__).resolve().parent / "webui.db"

_lock = threading.Lock()
# 内存中记录每个邀请码当前并发占用数，支持 1 个码 (max_uses=30) 被多个并发 worker 同时安全领用
_invite_inflight: dict[str, int] = {}

DEFAULT_MAIL_SOURCE = "icloud_relay"


_tls = threading.local()
_all_conns: list[sqlite3.Connection] = []
_conn_pool_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    target = str(DB_PATH)
    cache: dict = getattr(_tls, "conns", None)
    if cache is None:
        cache = {}
        _tls.conns = cache
    con = cache.get(target)
    if con is None:
        con = sqlite3.connect(target, check_same_thread=False, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        cache[target] = con
        with _conn_pool_lock:
            _all_conns.append(con)
    return con


def close_connections() -> None:
    """关闭所有线程缓存的 SQLite 连接（供测试清理或退出时释放 Windows 文件句柄）。"""
    with _conn_pool_lock:
        conns = list(_all_conns)
        _all_conns.clear()
    for c in conns:
        try:
            c.close()
        except Exception:
            pass
    if hasattr(_tls, "conns"):
        _tls.conns.clear()


def init_db():
    con = _conn()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS outlook_accounts (
            email           TEXT PRIMARY KEY,
            password        TEXT,
            client_id       TEXT,
            refresh_token   TEXT,
            relay_url       TEXT,
            kind            TEXT NOT NULL DEFAULT 'icloud_relay',
            status          TEXT NOT NULL DEFAULT 'available',
            imported_at     REAL,
            claimed_at      REAL,
            finished_at     REAL,
            fail_reason     TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_outlook_status ON outlook_accounts(status);

        CREATE TABLE IF NOT EXISTS settings (
            key     TEXT PRIMARY KEY,
            value   TEXT
        );

        CREATE TABLE IF NOT EXISTS registered (
            email               TEXT PRIMARY KEY,
            password            TEXT,
            account_id          TEXT,
            access_token        TEXT,
            session_token       TEXT,
            refresh_token       TEXT,
            id_token            TEXT,
            device_id           TEXT,
            csrf_token          TEXT,
            cookie_header       TEXT,
            totp_secret         TEXT,
            totp_factor_id      TEXT,
            status              TEXT,
            stage               TEXT,
            own_code            TEXT,
            used_invite_code    TEXT,
            ip                  TEXT,
            extra_json          TEXT,
            created_at          REAL
        );

        CREATE TABLE IF NOT EXISTS runs (
            run_id          TEXT PRIMARY KEY,
            email           TEXT,
            status          TEXT,
            stage           TEXT,
            started_at      REAL,
            finished_at     REAL,
            log_path        TEXT,
            error           TEXT,
            error_category  TEXT
        );

        CREATE TABLE IF NOT EXISTS invite_codes (
            code        TEXT PRIMARY KEY,
            status      TEXT NOT NULL DEFAULT 'available',
            used_count  INTEGER NOT NULL DEFAULT 0,
            max_uses    INTEGER NOT NULL DEFAULT 30,
            source      TEXT DEFAULT 'manual',
            note        TEXT,
            created_at  REAL,
            updated_at  REAL
        );

        CREATE INDEX IF NOT EXISTS idx_invite_status ON invite_codes(status);
    """)
    con.commit()

    # 增量列迁移（兼容存量空库或旧库）
    run_cols = {r[1] for r in con.execute("PRAGMA table_info(runs)").fetchall()}
    for col in ("error_category", "stage"):
        if col not in run_cols:
            con.execute(f"ALTER TABLE runs ADD COLUMN {col} TEXT")
            con.commit()

    acc_cols = {r[1] for r in con.execute("PRAGMA table_info(outlook_accounts)").fetchall()}
    if "kind" not in acc_cols:
        con.execute("ALTER TABLE outlook_accounts ADD COLUMN kind TEXT NOT NULL DEFAULT 'icloud_relay'")
        con.commit()
    if "relay_url" not in acc_cols:
        con.execute("ALTER TABLE outlook_accounts ADD COLUMN relay_url TEXT")
        con.commit()
    con.execute("CREATE INDEX IF NOT EXISTS idx_outlook_kind ON outlook_accounts(kind, status)")
    con.commit()

    reg_cols = {r[1] for r in con.execute("PRAGMA table_info(registered)").fetchall()}
    for col in (
        "totp_secret", "totp_factor_id", "account_id", "status",
        "stage", "own_code", "used_invite_code", "ip",
    ):
        if col not in reg_cols:
            con.execute(f"ALTER TABLE registered ADD COLUMN {col} TEXT")
            con.commit()


# ════════════════════════ 邮箱号池 ════════════════════════


def parse_lines(text: str, kind: str = "") -> list[dict]:
    from mail_providers import parse_import_text
    return parse_import_text(text or "", kind)


def import_accounts(text: str, kind: str = "") -> dict:
    rows = parse_lines(text, kind)
    now = time.time()
    inserted = updated = skipped = 0
    with _lock:
        con = _conn()
        for r in rows:
            row_kind = r.get("kind") or kind or DEFAULT_MAIL_SOURCE
            password = r.get("password", "") or ""
            client_id = r.get("client_id", "") or ""
            refresh = r.get("refresh_token", "") or ""
            relay = r.get("relay_url", "") or ""

            cur = con.execute(
                "SELECT refresh_token, relay_url, kind FROM outlook_accounts WHERE email=?",
                (r["email"],),
            )
            existing = cur.fetchone()
            if existing is None:
                con.execute(
                    "INSERT INTO outlook_accounts(email, password, client_id, refresh_token, "
                    "relay_url, kind, status, imported_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'available', ?)",
                    (r["email"], password, client_id, refresh, relay, row_kind, now),
                )
                inserted += 1
            elif (
                (existing["refresh_token"] or "") != refresh
                or (existing["relay_url"] or "") != relay
                or (existing["kind"] or "") != row_kind
            ):
                con.execute(
                    "UPDATE outlook_accounts SET refresh_token=?, password=?, client_id=?, "
                    "relay_url=?, kind=?, status='available', imported_at=?, fail_reason=NULL "
                    "WHERE email=?",
                    (refresh, password, client_id, relay, row_kind, now, r["email"]),
                )
                updated += 1
            else:
                skipped += 1
        con.commit()
    return {"parsed": len(rows), "inserted": inserted, "updated": updated, "skipped": skipped}


def count_accounts(status: str = "", kind: str = "") -> int:
    con = _conn()
    sql = "SELECT COUNT(*) FROM outlook_accounts"
    where, args = [], []
    if status:
        where.append("status=?")
        args.append(status)
    if kind:
        where.append("kind=?")
        args.append(kind.strip().lower())
    if where:
        sql += " WHERE " + " AND ".join(where)
    return con.execute(sql, args).fetchone()[0]


def list_accounts(status: str = "", limit: int = 50, offset: int = 0, kind: str = "") -> list[dict]:
    con = _conn()
    sql = "SELECT * FROM outlook_accounts"
    where, args = [], []
    if status:
        where.append("status=?")
        args.append(status)
    if kind:
        where.append("kind=?")
        args.append(kind.strip().lower())
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY imported_at DESC LIMIT ? OFFSET ?"
    args += [limit, offset]
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def stats_by_kind() -> dict:
    con = _conn()
    cur = con.execute(
        "SELECT kind, status, COUNT(*) AS n FROM outlook_accounts GROUP BY kind, status"
    )
    out: dict[str, dict] = {}
    for r in cur.fetchall():
        k = r["kind"] or DEFAULT_MAIL_SOURCE
        slot = out.setdefault(
            k, {"available": 0, "in_use": 0, "done": 0, "failed": 0, "total": 0}
        )
        slot[r["status"]] = r["n"]
        slot["total"] += r["n"]
    return out


def get_account(email: str) -> Optional[dict]:
    con = _conn()
    cur = con.execute("SELECT * FROM outlook_accounts WHERE email=?", (email.lower(),))
    row = cur.fetchone()
    return dict(row) if row else None


def claim_account(email: str) -> Optional[dict]:
    email = (email or "").strip().lower()
    if not email:
        return None
    with _lock:
        con = _conn()
        cur = con.execute(
            "SELECT * FROM outlook_accounts WHERE email=? AND status IN ('available', 'failed')",
            (email,),
        )
        row = cur.fetchone()
        if not row:
            return None
        rc = con.execute(
            "UPDATE outlook_accounts SET status='in_use', claimed_at=?, fail_reason=NULL "
            "WHERE email=? AND status IN ('available', 'failed')",
            (time.time(), email),
        )
        con.commit()
        if rc.rowcount != 1:
            return None
        return dict(row)


def claim_next(kind: str = "") -> Optional[dict]:
    k = (kind or "").strip().lower()
    with _lock:
        con = _conn()
        for _ in range(50):
            if k:
                cur = con.execute(
                    "SELECT * FROM outlook_accounts WHERE status='available' AND kind=? "
                    "ORDER BY imported_at ASC LIMIT 1",
                    (k,),
                )
            else:
                cur = con.execute(
                    "SELECT * FROM outlook_accounts WHERE status='available' "
                    "ORDER BY imported_at ASC LIMIT 1"
                )
            row = cur.fetchone()
            if not row:
                return None
            rc = con.execute(
                "UPDATE outlook_accounts SET status='in_use', claimed_at=? "
                "WHERE email=? AND status='available'",
                (time.time(), row["email"]),
            )
            con.commit()
            if rc.rowcount == 1:
                return dict(row)
        return None


def mark_done(email: str) -> None:
    with _lock:
        con = _conn()
        con.execute(
            "UPDATE outlook_accounts SET status='done', finished_at=?, fail_reason=NULL WHERE email=?",
            (time.time(), email.lower()),
        )
        con.commit()


def mark_failed(email: str, reason: str = "") -> None:
    with _lock:
        con = _conn()
        con.execute(
            "UPDATE outlook_accounts SET status='failed', finished_at=?, fail_reason=? WHERE email=?",
            (time.time(), (reason or "")[:500], email.lower()),
        )
        con.commit()


def release_unused(email: str) -> None:
    with _lock:
        con = _conn()
        con.execute(
            "UPDATE outlook_accounts SET status='available', claimed_at=NULL "
            "WHERE email=? AND status='in_use'",
            (email.lower(),),
        )
        con.commit()


def reset_to_available(email: str) -> bool:
    with _lock:
        con = _conn()
        rc = con.execute(
            "UPDATE outlook_accounts SET status='available', claimed_at=NULL, "
            "finished_at=NULL, fail_reason=NULL WHERE lower(email)=lower(?)",
            (email,),
        )
        con.commit()
        return rc.rowcount > 0


def bulk_reset_to_available(emails: list[str]) -> int:
    if not emails:
        return 0
    with _lock:
        con = _conn()
        rc = con.execute(
            f"UPDATE outlook_accounts SET status='available', claimed_at=NULL, "
            f"finished_at=NULL, fail_reason=NULL "
            f"WHERE lower(email) IN ({','.join(['lower(?)'] * len(emails))})",
            emails,
        )
        con.commit()
        return rc.rowcount


def reset_failed_to_available() -> int:
    with _lock:
        con = _conn()
        rc = con.execute(
            "UPDATE outlook_accounts SET status='available', fail_reason=NULL, "
            "finished_at=NULL WHERE status='failed'"
        )
        con.commit()
        return rc.rowcount


def release_stale_in_use(stale_seconds: float = 1800) -> int:
    with _lock:
        con = _conn()
        cutoff = time.time() - stale_seconds
        rc = con.execute(
            "UPDATE outlook_accounts SET status='available', claimed_at=NULL "
            "WHERE status='in_use' AND (claimed_at IS NULL OR claimed_at < ?)",
            (cutoff,),
        )
        con.commit()
        return rc.rowcount


def delete_account(email: str) -> bool:
    with _lock:
        con = _conn()
        rc = con.execute("DELETE FROM outlook_accounts WHERE email=?", (email.lower(),))
        con.commit()
        return rc.rowcount > 0


def delete_accounts_by_status(status: str) -> int:
    valid = {"available", "in_use", "done", "failed", "all"}
    s = (status or "").strip().lower()
    if s not in valid:
        return 0
    with _lock:
        con = _conn()
        if s == "all":
            rc = con.execute("DELETE FROM outlook_accounts")
        else:
            rc = con.execute("DELETE FROM outlook_accounts WHERE status=?", (s,))
        con.commit()
        return rc.rowcount


def delete_accounts_by_emails(emails: list[str]) -> int:
    cleaned = [e.strip().lower() for e in (emails or []) if e and e.strip()]
    if not cleaned:
        return 0
    with _lock:
        con = _conn()
        placeholders = ",".join("?" * len(cleaned))
        rc = con.execute(
            f"DELETE FROM outlook_accounts WHERE email IN ({placeholders})",
            cleaned,
        )
        con.commit()
        return rc.rowcount


def stats() -> dict:
    con = _conn()
    cur = con.execute(
        "SELECT status, COUNT(*) AS n FROM outlook_accounts GROUP BY status"
    )
    out = {"available": 0, "in_use": 0, "done": 0, "failed": 0, "total": 0}
    for r in cur.fetchall():
        out[r["status"]] = r["n"]
        out["total"] += r["n"]
    return out


# ════════════════════════ 邀请码池 (invite_codes) ════════════════════════


def _clean_code(raw: str) -> str:
    s = (raw or "").strip()
    if not s or s.startswith("#"):
        return ""
    # 允许带 URL 粘贴，如 https://muse.ai/?invite=XXXX 或纯邀请码
    m = re.search(r"[?&](?:invite|code)=([A-Za-z0-9_-]{4,64})", s, re.I)
    if m:
        return m.group(1)
    return s


def import_invite_codes(text_or_list, max_uses: int = 30, source: str = "manual") -> dict:
    if isinstance(text_or_list, str):
        lines = text_or_list.splitlines()
    else:
        lines = list(text_or_list or [])

    codes = []
    seen = set()
    for ln in lines:
        c = _clean_code(str(ln))
        if c and c not in seen:
            seen.add(c)
            codes.append(c)

    max_uses = max(1, int(max_uses or 30))
    now = time.time()
    inserted = skipped = 0
    with _lock:
        con = _conn()
        for c in codes:
            row = con.execute("SELECT code FROM invite_codes WHERE code=?", (c,)).fetchone()
            if row is None:
                con.execute(
                    "INSERT INTO invite_codes(code, status, used_count, max_uses, source, created_at, updated_at) "
                    "VALUES (?, 'available', 0, ?, ?, ?, ?)",
                    (c, max_uses, source, now, now),
                )
                inserted += 1
            else:
                skipped += 1
        con.commit()
    return {"parsed": len(codes), "inserted": inserted, "skipped": skipped}


def claim_invite_code() -> Optional[str]:
    """按先进先出领取一个还有余量的邀请码（支持同一码并发多次兑换直到 max_uses）。"""
    with _lock:
        con = _conn()
        rows = con.execute(
            "SELECT code, used_count, max_uses FROM invite_codes "
            "WHERE status='available' AND used_count < max_uses "
            "ORDER BY created_at ASC"
        ).fetchall()
        for r in rows:
            code = r["code"]
            inflight = _invite_inflight.get(code, 0)
            if r["used_count"] + inflight < r["max_uses"]:
                _invite_inflight[code] = inflight + 1
                return code
        return None


def finish_invite_code(code: str, ok: bool, reason: str = "") -> None:
    """回写邀请码兑换结果。"""
    code = (code or "").strip()
    if not code:
        return
    now = time.time()
    with _lock:
        if code in _invite_inflight:
            _invite_inflight[code] = max(0, _invite_inflight[code] - 1)
            if _invite_inflight[code] == 0:
                _invite_inflight.pop(code, None)

        con = _conn()
        row = con.execute(
            "SELECT used_count, max_uses, status FROM invite_codes WHERE code=?", (code,)
        ).fetchone()
        if not row:
            return
        if ok:
            new_used = int(row["used_count"] or 0) + 1
            new_status = "exhausted" if new_used >= int(row["max_uses"] or 30) else "available"
            con.execute(
                "UPDATE invite_codes SET used_count=?, status=?, updated_at=?, note=? WHERE code=?",
                (new_used, new_status, now, "redeemed", code),
            )
        elif reason == "used_up":
            con.execute(
                "UPDATE invite_codes SET status='exhausted', used_count=max_uses, updated_at=?, note=? WHERE code=?",
                (now, "服务端返回 used_up (已达30次上限)", code),
            )
        elif reason == "invalid":
            con.execute(
                "UPDATE invite_codes SET status='invalid', updated_at=?, note=? WHERE code=?",
                (now, "服务端返回 invalid (邀请码无效)", code),
            )
        con.commit()


def list_invite_codes(status: str = "", limit: int = 100, offset: int = 0) -> list[dict]:
    con = _conn()
    sql = "SELECT * FROM invite_codes"
    args: list = []
    if status:
        sql += " WHERE status=?"
        args.append(status.strip().lower())
    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    args += [limit, offset]
    rows = [dict(r) for r in con.execute(sql, args).fetchall()]
    with _lock:
        for r in rows:
            r["in_flight"] = _invite_inflight.get(r["code"], 0)
    return rows


def count_invite_codes(status: str = "") -> int:
    con = _conn()
    if status:
        return con.execute(
            "SELECT COUNT(*) FROM invite_codes WHERE status=?", (status.strip().lower(),)
        ).fetchone()[0]
    return con.execute("SELECT COUNT(*) FROM invite_codes").fetchone()[0]


def invite_stats() -> dict:
    con = _conn()
    cur = con.execute(
        "SELECT status, COUNT(*) AS n, "
        "SUM(CASE WHEN status='available' AND max_uses > used_count THEN (max_uses - used_count) ELSE 0 END) AS rem "
        "FROM invite_codes GROUP BY status"
    )
    out = {"available": 0, "exhausted": 0, "invalid": 0, "total": 0, "remaining_uses": 0}
    for r in cur.fetchall():
        st = r["status"]
        if st in out:
            out[st] = r["n"]
        out["total"] += r["n"]
        out["remaining_uses"] += int(r["rem"] or 0)
    return out


def delete_invite_codes(codes: Optional[list[str]] = None, status: str = "") -> int:
    with _lock:
        con = _conn()
        if status == "all":
            _invite_inflight.clear()
            rc = con.execute("DELETE FROM invite_codes")
            con.commit()
            return rc.rowcount
        if status:
            rc = con.execute("DELETE FROM invite_codes WHERE status=?", (status.strip().lower(),))
            con.commit()
            return rc.rowcount
        cleaned = [c.strip() for c in (codes or []) if c and c.strip()]
        if not cleaned:
            return 0
        for c in cleaned:
            _invite_inflight.pop(c, None)
        placeholders = ",".join("?" * len(cleaned))
        rc = con.execute(f"DELETE FROM invite_codes WHERE code IN ({placeholders})", cleaned)
        con.commit()
        return rc.rowcount


def reset_invite_codes(codes: Optional[list[str]] = None) -> int:
    now = time.time()
    with _lock:
        con = _conn()
        if codes:
            cleaned = [c.strip() for c in codes if c and c.strip()]
            if not cleaned:
                return 0
            placeholders = ",".join("?" * len(cleaned))
            rc = con.execute(
                f"UPDATE invite_codes SET status='available', used_count=0, note=NULL, updated_at=? "
                f"WHERE code IN ({placeholders})",
                [now, *cleaned],
            )
        else:
            rc = con.execute(
                "UPDATE invite_codes SET status='available', note=NULL, updated_at=? "
                "WHERE status IN ('exhausted', 'invalid') AND used_count < max_uses",
                (now,),
            )
        con.commit()
        return rc.rowcount


# ════════════════════════ 注册结果 (registered) ════════════════════════


_DIRECT_REG_COLS = {
    "email", "password", "account_id", "access_token", "session_token",
    "refresh_token", "id_token", "device_id", "csrf_token", "cookie_header",
    "totp_secret", "totp_factor_id", "status", "stage", "own_code",
    "used_invite_code", "ip",
}


def save_registered(d: dict) -> None:
    """保存或合并更新 Muse 注册结果（保留已有非空凭证与自有邀请码）。"""
    email = (d.get("email") or "").strip().lower()
    if not email:
        return

    extra_in = {k: v for k, v in d.items() if k not in _DIRECT_REG_COLS}
    with _lock:
        con = _conn()
        prev = con.execute("SELECT * FROM registered WHERE email=?", (email,)).fetchone()
        prev_dict = dict(prev) if prev else {}
        prev_extra = {}
        if prev_dict.get("extra_json"):
            try:
                prev_extra = json.loads(prev_dict["extra_json"])
            except Exception:
                prev_extra = {}

        merged_extra = {**prev_extra, **extra_in}

        def pick(key: str) -> str:
            val = str(d.get(key) or "").strip()
            if val:
                return val
            return str(prev_dict.get(key) or "").strip()

        session_token = pick("session_token")
        cookie_header = pick("cookie_header") or (f"hatch_sess={session_token}" if session_token else "")
        status = str(d.get("status") or "").strip() or str(prev_dict.get("status") or "activated")
        if prev_dict.get("status") == "redeemed" and status != "redeemed":
            status = "redeemed"

        con.execute(
            "INSERT OR REPLACE INTO registered "
            "(email, password, account_id, access_token, session_token, refresh_token, "
            "id_token, device_id, csrf_token, cookie_header, totp_secret, totp_factor_id, "
            "status, stage, own_code, used_invite_code, ip, extra_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                email,
                pick("password"),
                pick("account_id"),
                pick("access_token"),
                session_token,
                pick("refresh_token"),
                pick("id_token"),
                pick("device_id"),
                pick("csrf_token"),
                cookie_header,
                pick("totp_secret"),
                pick("totp_factor_id"),
                status,
                pick("stage"),
                pick("own_code"),
                pick("used_invite_code"),
                pick("ip"),
                json.dumps(merged_extra, ensure_ascii=False) if merged_extra else None,
                prev_dict.get("created_at") or time.time(),
            ),
        )
        con.commit()


def update_live_check(email: str, live_info: dict, own_code: str = "") -> None:
    email = (email or "").strip().lower()
    if not email:
        return
    with _lock:
        con = _conn()
        row = con.execute("SELECT extra_json, own_code FROM registered WHERE email=?", (email,)).fetchone()
        if not row:
            return
        extra = {}
        if row["extra_json"]:
            try:
                extra = json.loads(row["extra_json"])
            except Exception:
                extra = {}
        extra["live_check"] = live_info
        final_own = (own_code or "").strip() or (row["own_code"] or "").strip()
        con.execute(
            "UPDATE registered SET extra_json=?, own_code=? WHERE email=?",
            (json.dumps(extra, ensure_ascii=False), final_own, email),
        )
        con.commit()


def update_redemption(
    email: str,
    *,
    status: str,
    used_code: str = "",
    own_code: str = "",
    session_token: str = "",
    vm_id: str = "",
) -> None:
    email = (email or "").strip().lower()
    if not email:
        return
    with _lock:
        con = _conn()
        row = con.execute("SELECT * FROM registered WHERE email=?", (email,)).fetchone()
        if not row:
            return
        final_sess = (session_token or "").strip() or (row["session_token"] or "")
        final_cookie = f"hatch_sess={final_sess}" if final_sess else (row["cookie_header"] or "")
        final_own = (own_code or "").strip() or (row["own_code"] or "")
        final_used = (used_code or "").strip() or (row["used_invite_code"] or "")
        final_vm = (vm_id or "").strip() or (row["device_id"] or "")
        con.execute(
            "UPDATE registered SET status=?, stage='own_code', used_invite_code=?, "
            "own_code=?, session_token=?, cookie_header=?, device_id=? WHERE email=?",
            (status, final_used, final_own, final_sess, final_cookie, final_vm, email),
        )
        con.commit()


def _registered_where(filt: str) -> str:
    if filt == "redeemed":
        return "WHERE status = 'redeemed'"
    if filt == "has_own_code":
        return "WHERE length(coalesce(own_code, '')) > 0"
    if filt == "activated":
        return "WHERE status IN ('activated', 'registered_pending_redemption')"
    if filt == "waitlist":
        return "WHERE status = 'registered_waitlist'"
    if filt == "unchecked":
        return "WHERE (extra_json IS NULL OR extra_json NOT LIKE '%\"live_check\"%')"
    if filt == "live":
        return "WHERE extra_json LIKE '%\"status\": \"live\"%' OR extra_json LIKE '%\"status\":\"live\"%'"
    if filt == "token_invalid":
        return (
            "WHERE extra_json LIKE '%\"token_invalid\"%' "
            "OR extra_json LIKE '%\"forbidden\"%'"
        )
    return ""


def count_registered(filter_rt: str = "all") -> int:
    con = _conn()
    cur = con.execute(f"SELECT COUNT(*) FROM registered {_registered_where(filter_rt)}")
    return cur.fetchone()[0]


def registered_stats() -> dict:
    con = _conn()
    total = con.execute("SELECT COUNT(*) FROM registered").fetchone()[0]
    redeemed = con.execute("SELECT COUNT(*) FROM registered WHERE status='redeemed'").fetchone()[0]
    activated = con.execute(
        "SELECT COUNT(*) FROM registered WHERE status IN ('activated', 'registered_pending_redemption')"
    ).fetchone()[0]
    waitlist = con.execute(
        "SELECT COUNT(*) FROM registered WHERE status='registered_waitlist'"
    ).fetchone()[0]
    own_codes = con.execute(
        "SELECT COUNT(*) FROM registered WHERE length(coalesce(own_code, '')) > 0"
    ).fetchone()[0]
    return {
        "total": total,
        "redeemed": redeemed,
        "activated": activated,
        "waitlist": waitlist,
        "own_codes": own_codes,
    }


def list_registered(limit: int = 20, offset: int = 0, filter_rt: str = "all") -> list[dict]:
    con = _conn()
    where = _registered_where(filter_rt)
    cur = con.execute(
        f"SELECT email, account_id, status, stage, own_code, used_invite_code, ip, "
        f"device_id, length(access_token) AS at_len, length(session_token) AS st_len, "
        f"(CASE WHEN length(trim(coalesce(access_token, ''))) > 0 THEN 1 ELSE 0 END + "
        f"CASE WHEN length(trim(coalesce(session_token, ''))) > 0 THEN 1 ELSE 0 END + "
        f"CASE WHEN length(trim(coalesce(refresh_token, ''))) > 0 THEN 1 ELSE 0 END + "
        f"CASE WHEN length(trim(coalesce(id_token, ''))) > 0 THEN 1 ELSE 0 END + "
        f"CASE WHEN length(trim(coalesce(csrf_token, ''))) > 0 THEN 1 ELSE 0 END) AS token_count, "
        f"extra_json, created_at FROM registered "
        f"{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = []
    for r in cur.fetchall():
        d = dict(r)
        live_check = None
        persona = ""
        if d.get("extra_json"):
            try:
                extra = json.loads(d["extra_json"])
                live_check = extra.get("live_check")
                ln = extra.get("last_name") or ""
                fn = extra.get("first_name") or ""
                if ln or fn:
                    persona = f"{ln} {fn}".strip()
            except Exception:
                pass
        d["live_check"] = live_check
        d["persona"] = persona
        d.pop("extra_json", None)
        rows.append(d)
    return rows


def list_registered_full(limit: int = 5000) -> list[dict]:
    con = _conn()
    cur = con.execute(
        "SELECT r.*, a.relay_url AS relay_url "
        "FROM registered r LEFT JOIN outlook_accounts a ON a.email = r.email "
        "ORDER BY r.created_at DESC LIMIT ?",
        (limit,),
    )
    out = []
    for row in cur.fetchall():
        d = dict(row)
        if d.get("extra_json"):
            try:
                d["extra"] = json.loads(d["extra_json"])
            except Exception:
                d["extra"] = {}
        else:
            d["extra"] = {}
        d.pop("extra_json", None)
        out.append(d)
    return out


def list_registered_by_emails(emails: list[str]) -> list[dict]:
    cleaned = [e.strip().lower() for e in (emails or []) if e and e.strip()]
    if not cleaned:
        return []

    con = _conn()
    out = []
    CHUNK = 500
    for i in range(0, len(cleaned), CHUNK):
        part = cleaned[i:i + CHUNK]
        placeholders = ",".join("?" * len(part))
        cur = con.execute(
            f"SELECT r.*, a.relay_url AS relay_url "
            f"FROM registered r LEFT JOIN outlook_accounts a ON a.email = r.email "
            f"WHERE r.email IN ({placeholders})",
            part,
        )
        for row in cur.fetchall():
            d = dict(row)
            if d.get("extra_json"):
                try:
                    d["extra"] = json.loads(d["extra_json"])
                except Exception:
                    d["extra"] = {}
            else:
                d["extra"] = {}
            d.pop("extra_json", None)
            out.append(d)

    out.sort(key=lambda d: d.get("created_at") or 0, reverse=True)
    return out


def get_registered(email: str) -> Optional[dict]:
    con = _conn()
    cur = con.execute(
        "SELECT r.*, a.relay_url AS relay_url "
        "FROM registered r LEFT JOIN outlook_accounts a ON a.email = r.email "
        "WHERE r.email=?",
        (email.lower(),),
    )
    row = cur.fetchone()
    if not row:
        return None
    out = dict(row)
    if out.get("extra_json"):
        try:
            out["extra"] = json.loads(out["extra_json"])
        except Exception:
            out["extra"] = {}
    else:
        out["extra"] = {}
    out.pop("extra_json", None)
    return out


def delete_registered(email: str) -> bool:
    with _lock:
        con = _conn()
        rc = con.execute("DELETE FROM registered WHERE email=?", (email.lower(),))
        con.commit()
        return rc.rowcount > 0


def delete_registered_by_emails(emails: list[str]) -> int:
    cleaned = [e.strip().lower() for e in (emails or []) if e and e.strip()]
    if not cleaned:
        return 0
    with _lock:
        con = _conn()
        placeholders = ",".join("?" * len(cleaned))
        rc = con.execute(
            f"DELETE FROM registered WHERE email IN ({placeholders})",
            cleaned,
        )
        con.commit()
        return rc.rowcount


def delete_all_registered() -> int:
    with _lock:
        con = _conn()
        rc = con.execute("DELETE FROM registered")
        con.commit()
        return rc.rowcount


# ════════════════════════ 运行记录 (runs) ════════════════════════


def create_run(run_id: str, email: str, log_path: str) -> None:
    with _lock:
        con = _conn()
        con.execute(
            "INSERT INTO runs(run_id, email, status, stage, started_at, log_path) "
            "VALUES (?, ?, 'running', 'initialized', ?, ?)",
            (run_id, email.lower(), time.time(), log_path),
        )
        con.commit()


def finish_run(
    run_id: str,
    status: str,
    error: str = "",
    category: str = "",
    stage: str = "",
    email: str = "",
) -> None:
    with _lock:
        con = _conn()
        if email:
            con.execute(
                "UPDATE runs SET email=?, status=?, stage=?, finished_at=?, error=?, error_category=? WHERE run_id=?",
                (email.lower(), status, stage or None, time.time(), (error or "")[:500], category or None, run_id),
            )
        else:
            con.execute(
                "UPDATE runs SET status=?, stage=?, finished_at=?, error=?, error_category=? WHERE run_id=?",
                (status, stage or None, time.time(), (error or "")[:500], category or None, run_id),
            )
        con.commit()


def get_run(run_id: str) -> Optional[dict]:
    con = _conn()
    row = con.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    return dict(row) if row else None


def list_runs(limit: int = 50) -> list[dict]:
    con = _conn()
    cur = con.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,))
    return [dict(r) for r in cur.fetchall()]


# ════════════════════════ 配置 (settings) ════════════════════════


def get_setting(key: str, default: str = "") -> str:
    con = _conn()
    cur = con.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    return row["value"] if row else default


def set_setting(key: str, value) -> None:
    with _lock:
        con = _conn()
        con.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        con.commit()


def get_proxy_pool() -> dict:
    raw = get_setting("proxy_pool", None)
    if raw is None:
        return {"proxies": [], "configured": False}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        parsed = []
    if not isinstance(parsed, list):
        parsed = []
    proxies = list(dict.fromkeys(
        line.strip()
        for value in parsed
        if isinstance(value, str)
        for line in value.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ))
    return {"proxies": proxies, "configured": True}


def save_proxy_pool(proxies: list[str]) -> list[str]:
    cleaned = list(dict.fromkeys(
        line.strip()
        for value in (proxies or [])
        if isinstance(value, str)
        for line in value.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ))
    set_setting("proxy_pool", json.dumps(cleaned, ensure_ascii=False))
    return cleaned


def get_mail_config() -> dict:
    from mail_providers import list_providers

    out = {"mail_source": get_setting("mail_source", DEFAULT_MAIL_SOURCE)}
    for p in list_providers():
        for f in p["config_fields"]:
            key = f["key"]
            if f.get("type") == "password":
                out[key] = "***" if get_setting(key) else ""
            else:
                out[key] = get_setting(key, "")
    return out


def save_mail_config(data: dict) -> None:
    from mail_providers import get_provider_class, list_providers

    if "mail_source" in data:
        src = str(data["mail_source"]).strip().lower()
        get_provider_class(src)
        set_setting("mail_source", src)

    for p in list_providers():
        for f in p["config_fields"]:
            key = f["key"]
            if key not in data:
                continue
            val = data[key]
            if f.get("type") == "password":
                if not val or val == "***":
                    continue
            set_setting(key, str(val).strip())


def get_mail_settings() -> dict:
    from mail_providers import list_providers

    out = {"mail_source": get_setting("mail_source", DEFAULT_MAIL_SOURCE)}
    for p in list_providers():
        for f in p["config_fields"]:
            out[f["key"]] = get_setting(f["key"], "")
    return out


init_db()
