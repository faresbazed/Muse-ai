"""Muse 批量注册 WebUI FastAPI 主服务（默认监听 127.0.0.1:8766）。"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from auth_flow import check_account_live, redeem_registered_account  # noqa: E402
from mail_providers import (  # noqa: E402
    ImportValidationError,
    MailProviderError,
    create_mail_provider,
    get_provider_class,
    list_pooled_providers,
    list_providers,
)

from . import db, export_formats, registrar  # noqa: E402
from .auto_loop import CONTROLLER as AUTO_LOOP  # noqa: E402

try:
    _released = db.release_stale_in_use(stale_seconds=1800)
    if _released > 0:
        logging.getLogger("webui").info(f"[startup] 释放 {_released} 个卡死的 in_use 邮箱")
except Exception as _e:
    logging.getLogger("webui").warning(f"[startup] release_stale 失败: {_e}")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("webui")

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Muse Register WebUI", docs_url=None, redoc_url=None)


# ════════════════════════ 请求模型 ════════════════════════


class ImportReq(BaseModel):
    text: str = Field(..., description="每行一个邮箱凭证")
    kind: str = Field("", description="邮箱来源标识")


class SyncLocalIcloudReq(BaseModel):
    limit: int = Field(0, description="最多同步多少个 unused 邮箱，0=全部")


class RegisterReq(BaseModel):
    email: Optional[str] = Field(None, description="留空 = 自动 claim 下一个 available")
    proxy: str = ""
    otp_timeout: int = 45
    lang: str = "ja"
    impersonate: str = "chrome142"
    first_name: str = ""
    last_name: str = ""
    date_of_birth: str = ""
    send_caa: bool = True
    send_falco: bool = True
    resolve_ip: bool = True
    redeem_mode: str = "pool"         # "pool" | "single" | "none"
    invite_code: str = ""
    auto_pool_own_code: bool = True


class AutoLoopStartReq(BaseModel):
    proxy: str = ""
    proxy_pool: str = ""
    concurrency: int = 3
    max_per_ip: int = 2
    otp_timeout: int = 120
    cool_down_seconds: float = 1.0
    target_count: int = 0
    lang: str = "ja"
    impersonate: str = "chrome142"
    send_caa: bool = True
    send_falco: bool = True
    resolve_ip: bool = True
    redeem_mode: str = "pool"         # "pool" | "none"
    auto_pool_own_code: bool = True
    stop_on_reject: bool = True


class InviteImportReq(BaseModel):
    text: str
    max_uses: int = 30


class InviteBulkDeleteReq(BaseModel):
    codes: Optional[list[str]] = None
    status: str = ""


class InviteResetReq(BaseModel):
    codes: Optional[list[str]] = None


class CheckLiveReq(BaseModel):
    emails: list[str]
    proxy: str = ""
    fetch_own_code: bool = True
    auto_pool_own_code: bool = False


class RedeemAccountReq(BaseModel):
    emails: list[str]
    redeem_mode: str = "pool"         # "pool" | "single"
    invite_code: str = ""
    proxy: str = ""
    auto_pool_own_code: bool = True


class BulkDeleteReq(BaseModel):
    status: Optional[str] = None
    emails: Optional[list[str]] = None


class BulkResetReq(BaseModel):
    emails: list[str]


class ProxyTestReq(BaseModel):
    proxies: list[str]
    timeout: int = 8
    test_url: str = "https://api.ipify.org?format=json"


class ProxyPoolReq(BaseModel):
    proxies: list[str]


class BulkDeleteRegisteredReq(BaseModel):
    emails: Optional[list[str]] = None
    all: bool = False


class ExportRegisteredReq(BaseModel):
    format: str
    emails: Optional[list[str]] = None
    all: bool = False


class SaveMailConfigReq(BaseModel):
    model_config = {"extra": "allow"}
    mail_source: Optional[str] = None


# ════════════════════════ 统计与健康检查 ════════════════════════


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "stats": db.stats(),
        "invites": db.invite_stats(),
        "registered": db.registered_stats(),
    }


@app.get("/api/stats")
def api_stats():
    return {
        "ok": True,
        "stats": db.stats(),
        "invites": db.invite_stats(),
        "registered": db.registered_stats(),
    }


# ════════════════════════ 邮箱池管理 ════════════════════════


@app.post("/api/import")
def api_import(req: ImportReq):
    try:
        result = db.import_accounts(req.text, kind=req.kind)
    except ImportValidationError as e:
        return JSONResponse(
            status_code=422,
            content={"ok": False, "message": str(e), "errors": e.errors},
        )
    except MailProviderError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, **result, "stats": db.stats()}


@app.post("/api/import/icloud_local")
def api_import_icloud_local(req: SyncLocalIcloudReq):
    """一键从本地 icloud 服务 (4173) 同步 unused 隐藏邮箱到号池。"""
    try:
        from import_icloud import sync_icloud_to_muse
        res = sync_icloud_to_muse(limit=req.limit)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"同步本地 iCloud 邮箱失败: {e}")
    return {"ok": True, **res, "stats": db.stats()}


@app.get("/api/accounts")
def api_accounts(
    status: str = "",
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    kind: str = "",
):
    # List screens need metadata only, never mailbox credentials or private OTP URLs.
    metadata = {"email", "kind", "status", "imported_at", "claimed_at", "finished_at", "fail_reason"}
    items = [
        {key: value for key, value in row.items() if key in metadata}
        for row in db.list_accounts(status=status, limit=limit, offset=offset, kind=kind)
    ]
    total = db.count_accounts(status=status, kind=kind)
    return {
        "ok": True,
        "items": items,
        "total": total,
        "by_kind": db.stats_by_kind(),
    }


@app.delete("/api/accounts/{email}")
def api_delete_account(email: str):
    if not db.delete_account(email):
        raise HTTPException(404, "not found")
    return {"ok": True}


@app.post("/api/accounts/bulk_delete")
def api_bulk_delete(req: BulkDeleteReq):
    if req.status:
        n = db.delete_accounts_by_status(req.status)
        return {"ok": True, "deleted": n, "by": "status", "stats": db.stats()}
    if req.emails:
        n = db.delete_accounts_by_emails(req.emails)
        return {"ok": True, "deleted": n, "by": "emails", "stats": db.stats()}
    raise HTTPException(400, "需要 status 或 emails")


@app.post("/api/accounts/reset_failed")
def api_reset_failed():
    n = db.reset_failed_to_available()
    return {"ok": True, "reset": n, "stats": db.stats()}


@app.post("/api/accounts/reset/{email}")
def api_reset_account(email: str):
    if not db.reset_to_available(email):
        raise HTTPException(404, f"邮箱 {email} 不存在")
    return {"ok": True, "email": email}


@app.post("/api/accounts/bulk_reset")
def api_bulk_reset(req: BulkResetReq):
    if not req.emails:
        raise HTTPException(400, "emails 不能为空")
    n = db.bulk_reset_to_available(req.emails)
    return {"ok": True, "reset": n, "stats": db.stats()}


@app.post("/api/accounts/release_stale")
def api_release_stale(stale_seconds: int = Query(1800, ge=60)):
    n = db.release_stale_in_use(stale_seconds=stale_seconds)
    return {"ok": True, "released": n, "stats": db.stats()}


# ════════════════════════ 邀请码池管理 ════════════════════════


@app.get("/api/invites")
def api_list_invites(
    status: str = "",
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    return {
        "ok": True,
        "items": db.list_invite_codes(status=status, limit=limit, offset=offset),
        "total": db.count_invite_codes(status=status),
        "stats": db.invite_stats(),
    }


@app.get("/api/invites/stats")
def api_invite_stats():
    return {"ok": True, "stats": db.invite_stats()}


@app.post("/api/invites/import")
def api_import_invites(req: InviteImportReq):
    if not (req.text or "").strip():
        raise HTTPException(400, "请输入邀请码")
    res = db.import_invite_codes(req.text, max_uses=req.max_uses, source="manual")
    return {"ok": True, **res, "stats": db.invite_stats()}


@app.post("/api/invites/bulk_delete")
def api_delete_invites(req: InviteBulkDeleteReq):
    n = db.delete_invite_codes(codes=req.codes, status=req.status)
    return {"ok": True, "deleted": n, "stats": db.invite_stats()}


@app.post("/api/invites/reset")
def api_reset_invites(req: InviteResetReq):
    n = db.reset_invite_codes(codes=req.codes)
    return {"ok": True, "reset": n, "stats": db.invite_stats()}


# ════════════════════════ 代理连通性测试 ════════════════════════


@app.get("/api/settings/proxy")
def api_get_proxy_pool():
    return {"ok": True, **db.get_proxy_pool()}


@app.post("/api/settings/proxy")
def api_save_proxy_pool(req: ProxyPoolReq):
    proxies = db.save_proxy_pool(req.proxies)
    return {"ok": True, "proxies": proxies, "configured": True, "count": len(proxies)}


@app.post("/api/proxy/test")
def api_proxy_test(req: ProxyTestReq):
    from http_client import create_http_session

    timeout = max(1, min(int(req.timeout or 8), 60))
    test_url = (req.test_url or "https://api.ipify.org?format=json").strip()
    proxies = [p.strip() for p in (req.proxies or []) if p and p.strip()]
    if not proxies:
        raise HTTPException(400, "proxies 不能为空")

    def _test_one(proxy: str):
        t0 = time.perf_counter()
        sess = None
        try:
            sess = create_http_session(proxy=proxy, impersonate="chrome142")
            resp = sess.get(test_url, timeout=timeout)
            latency = int((time.perf_counter() - t0) * 1000)
            if resp.status_code != 200:
                return {"ok": False, "latency_ms": latency, "error": f"HTTP {resp.status_code}"}
            try:
                ip = resp.json().get("ip", "")
            except Exception:
                ip = (resp.text or "").strip()[:64]
            return {"ok": True, "latency_ms": latency, "ip": ip}
        except Exception as e:
            latency = int((time.perf_counter() - t0) * 1000)
            return {"ok": False, "latency_ms": latency, "error": str(e)[:140]}
        finally:
            if sess is not None:
                try:
                    sess.close()
                except Exception:
                    pass

    results = {}
    with ThreadPoolExecutor(max_workers=min(20, len(proxies))) as ex:
        for proxy, res in zip(proxies, ex.map(_test_one, proxies)):
            results[proxy] = res
    return {"ok": True, "results": results}


# ════════════════════════ 单次注册与 SSE 流 ════════════════════════


@app.post("/api/register")
def api_register(req: RegisterReq):
    mail_source = db.get_setting("mail_source", db.DEFAULT_MAIL_SOURCE)
    try:
        provider_cls = get_provider_class(mail_source)
    except MailProviderError as e:
        raise HTTPException(400, str(e))

    if not provider_cls.pooled:
        account = {
            "email": f"{mail_source}_placeholder_{int(time.time())}@placeholder.local",
            "password": "",
            "client_id": "",
            "refresh_token": "",
            "relay_url": "",
            "kind": mail_source,
        }
    elif req.email:
        account = db.claim_account(req.email)
        if not account:
            raise HTTPException(400, f"邮箱 {req.email} 不可用（不存在 / 正在使用 / 已完成）")
        if (account.get("kind") or db.DEFAULT_MAIL_SOURCE) != mail_source:
            db.release_unused(account["email"])
            raise HTTPException(
                400,
                f"{req.email} 是 {account.get('kind')} 类型，当前邮箱来源设为 {mail_source}，请先切换邮箱来源",
            )
    else:
        account = db.claim_next(kind=mail_source)
        if not account:
            raise HTTPException(
                400,
                f"号池中没有可用的 {provider_cls.display_name} 邮箱；请先去「导入邮箱」添加",
            )

    options = req.model_dump()
    run_id = registrar.start_registration(account, options)
    logger.info(f"[run] {run_id} -> {account['email']} (mail_source={mail_source})")
    return {"ok": True, "run_id": run_id, "email": account["email"]}


@app.get("/api/runs/{run_id}/stream")
async def api_stream(run_id: str, request: Request):
    q = registrar.get_run_queue(run_id)
    if q is None:
        raise HTTPException(404, "run_id not found or finished")

    async def event_gen():
        loop = asyncio.get_event_loop()
        try:
            while True:
                if await request.is_disconnected():
                    break
                msg = await loop.run_in_executor(None, _safe_get, q)
                if msg is None:
                    yield "event: end\ndata: {}\n\n"
                    break
                if not msg:
                    yield ": heartbeat\n\n"
                    continue
                if msg.startswith("__EVENT__:"):
                    yield f"event: status\ndata: {msg[len('__EVENT__:'):]}\n\n"
                else:
                    yield f"event: log\ndata: {json.dumps({'line': msg}, ensure_ascii=False)}\n\n"
        finally:
            registrar.remove_run_queue(run_id)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _safe_get(q):
    try:
        return q.get(timeout=45)
    except Exception:
        return ""


@app.get("/api/runs")
def api_runs(limit: int = Query(50, ge=1, le=1000)):
    return {"ok": True, "items": db.list_runs(limit=limit)}


# ════════════════════════ 注册结果、测活、补兑与导出 ════════════════════════


@app.get("/api/registered")
def api_registered(
    limit: int = Query(20, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    filter: str = "all",
):
    items = db.list_registered(limit=limit, offset=offset, filter_rt=filter)
    total = db.count_registered(filter_rt=filter)
    return {
        "ok": True,
        "items": items,
        "total": total,
        "summary": db.registered_stats(),
    }


@app.get("/api/registered/export/formats")
def api_export_formats():
    return {"ok": True, "formats": export_formats.list_formats()}


@app.post("/api/registered/export")
def api_export_registered(req: ExportRegisteredReq):
    fmt = export_formats.get_format(req.format)
    if fmt is None:
        raise HTTPException(400, f"未知导出格式: {req.format}")

    if req.all:
        rows = db.list_registered_full(limit=100000)
    elif req.emails:
        rows = db.list_registered_by_emails(req.emails)
    else:
        raise HTTPException(400, "需要 emails 或 all=true")

    base = {
        "ok": True,
        "count": len(rows),
        "filename": fmt.filename,
        "label": fmt.label,
        "mode": fmt.mode,
        "mime": fmt.mime,
        "emails": [(r.get("email") or "") for r in rows],
    }

    if fmt.mode == "download":
        blob = export_formats.render_bytes(rows, fmt)
        return {**base, "b64": base64.b64encode(blob).decode("ascii"), "size": len(blob)}

    return {**base, "text": export_formats.render_text(rows, fmt)}


@app.post("/api/registered/check_live")
def api_check_live(req: CheckLiveReq):
    """用已存 hatch_sess 请求 GET /api/hatch/invite 检测 Muse 账号存活与权限，并可同步提取自有邀请码。"""
    if not req.emails:
        raise HTTPException(400, "emails 不能为空")

    proxy = (req.proxy or "").strip() or None
    checked_at = time.time()
    results = {}
    pooled_new = 0

    for email in req.emails:
        cred = db.get_registered(email)
        if not cred:
            results[email] = {"status": "not_found", "label": "未找到"}
            continue
        try:
            info = check_account_live(
                cred, proxy=proxy, fetch_own_code=req.fetch_own_code
            )
        except Exception as e:
            results[email] = {"status": "error", "label": f"网络错误"}
            logger.warning(f"[check_live] {email} 检测失败: {e}")
            continue

        own = info.get("own_code") or ""
        results[email] = info
        if info["status"] not in ("not_found", "no_session", "error"):
            db.update_live_check(
                email,
                {"status": info["status"], "label": info["label"], "checked_at": checked_at},
                own_code=own,
            )
            if own and req.auto_pool_own_code:
                r_imp = db.import_invite_codes([own], max_uses=30, source=f"check:{email}")
                pooled_new += int(r_imp.get("inserted") or 0)

    return {"ok": True, "results": results, "pooled_new": pooled_new}


@app.post("/api/registered/redeem")
def api_redeem_registered(req: RedeemAccountReq):
    """对已注册但尚未兑换邀请码的账号执行 wake_vm + redeem + scratch_code。"""
    if not req.emails:
        raise HTTPException(400, "emails 不能为空")
    proxy = (req.proxy or "").strip() or None
    mode = (req.redeem_mode or "pool").strip().lower()
    fixed_code = (req.invite_code or "").strip()
    if mode == "single" and not fixed_code:
        raise HTTPException(400, "指定兑换模式下请填写邀请码")

    details = {}
    ok_count = 0
    fail_count = 0
    harvested = []

    for email in req.emails:
        cred = db.get_registered(email)
        if not cred:
            details[email] = {"ok": False, "reason": "not_found"}
            fail_count += 1
            continue

        code = fixed_code if mode == "single" else db.claim_invite_code()
        if not code:
            details[email] = {"ok": False, "reason": "no_available_invite_code"}
            fail_count += 1
            continue

        try:
            res = redeem_registered_account(cred, code, proxy=proxy)
        except Exception as e:
            if mode == "pool":
                db.finish_invite_code(code, False, "network_error")
            details[email] = {"ok": False, "reason": str(e)[:120]}
            fail_count += 1
            continue

        if mode == "pool":
            db.finish_invite_code(code, res["ok"] and res["reason"] == "redeemed", res["reason"])

        if res["ok"]:
            ok_count += 1
            own = res.get("own_code") or ""
            db.update_redemption(
                email,
                status="redeemed",
                used_code=code,
                own_code=own,
                session_token=res.get("session_token") or "",
                vm_id=res.get("vm_id") or "",
            )
            db.mark_done(email)
            if own:
                harvested.append(own)
                if req.auto_pool_own_code:
                    db.import_invite_codes([own], max_uses=30, source=f"redeem:{email}")
            details[email] = {"ok": True, "reason": res["reason"], "own_code": own}
        else:
            fail_count += 1
            details[email] = {"ok": False, "reason": res["reason"]}

    return {
        "ok": True,
        "redeemed": ok_count,
        "failed": fail_count,
        "harvested_codes": harvested,
        "details": details,
    }


@app.get("/api/registered/{email}")
def api_registered_one(email: str):
    row = db.get_registered(email)
    if not row:
        raise HTTPException(404, "not found")
    return {"ok": True, "data": row}


@app.delete("/api/registered/{email}")
def api_delete_registered(email: str):
    if not db.delete_registered(email):
        raise HTTPException(404, "not found")
    return {"ok": True}


@app.post("/api/registered/bulk_delete")
def api_bulk_delete_registered(req: BulkDeleteRegisteredReq):
    if req.all:
        n = db.delete_all_registered()
        return {"ok": True, "deleted": n, "by": "all"}
    if req.emails:
        n = db.delete_registered_by_emails(req.emails)
        return {"ok": True, "deleted": n, "by": "emails"}
    raise HTTPException(400, "需要 emails 或 all=true")


# ════════════════════════ 邮箱来源配置 ════════════════════════


@app.get("/api/mail/providers")
def api_mail_providers(pooled_only: bool = False):
    return {
        "ok": True,
        "providers": list_pooled_providers() if pooled_only else list_providers(),
        "current": db.get_setting("mail_source", db.DEFAULT_MAIL_SOURCE),
    }


@app.get("/api/settings/mail")
def api_get_mail_config():
    return {"ok": True, "config": db.get_mail_config()}


@app.post("/api/settings/mail")
def api_save_mail_config(req: SaveMailConfigReq):
    try:
        db.save_mail_config(req.model_dump(exclude_none=True))
    except MailProviderError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "config": db.get_mail_config()}


@app.post("/api/settings/mail/test")
def api_test_mail():
    mail_source = db.get_setting("mail_source", db.DEFAULT_MAIL_SOURCE)
    try:
        provider_cls = get_provider_class(mail_source)
    except MailProviderError as e:
        raise HTTPException(400, str(e))

    if provider_cls.pooled:
        raise HTTPException(
            400,
            f"{provider_cls.display_name} 属于号池类型，导入时自动校验格式，无需单独测试全局连通性",
        )

    try:
        provider = create_mail_provider(mail_source, db.get_mail_settings())
        result = provider.self_test()
    except Exception as e:
        raise HTTPException(500, f"测试失败: {e}")

    if not result.get("ok"):
        raise HTTPException(500, result.get("message") or "连接失败")
    return {"ok": True, "message": result.get("message", "连接成功")}


# ════════════════════════ 自动批量调度 ════════════════════════


@app.post("/api/auto/start")
def api_auto_start(req: AutoLoopStartReq):
    res = AUTO_LOOP.start(req.model_dump())
    if not res.get("ok"):
        raise HTTPException(400, res.get("error", "启动失败"))
    return res


@app.post("/api/auto/pause")
def api_auto_pause():
    res = AUTO_LOOP.pause()
    if not res.get("ok"):
        raise HTTPException(400, res.get("error", "暂停失败"))
    return res


@app.post("/api/auto/resume")
def api_auto_resume():
    res = AUTO_LOOP.resume()
    if not res.get("ok"):
        raise HTTPException(400, res.get("error", "恢复失败"))
    return res


@app.post("/api/auto/stop")
def api_auto_stop():
    res = AUTO_LOOP.stop()
    if not res.get("ok"):
        raise HTTPException(400, res.get("error", "停止失败"))
    return res


@app.get("/api/auto/status")
def api_auto_status():
    return {"ok": True, **AUTO_LOOP.status()}


@app.get("/api/auto/stream")
async def api_auto_stream(request: Request):
    q = AUTO_LOOP.subscribe()

    async def gen():
        loop = asyncio.get_event_loop()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await loop.run_in_executor(None, lambda: q.get(timeout=30))
                except Exception:
                    yield ": heartbeat\n\n"
                    continue
                if msg is None:
                    break
                kind = msg.get("kind", "state")
                data = msg.get("data", {})
                yield f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        finally:
            AUTO_LOOP.unsubscribe(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ════════════════════════ 静态资源 ════════════════════════


@app.get("/")
def root():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("webui.app:app", host="127.0.0.1", port=8766, reload=False)
