from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import httpx
import hashlib
import hmac
import time
import base64
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

app = FastAPI(title="미발송 주문 대시보드")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────
# Request Models
# ─────────────────────────────────────────

class NaverCredentials(BaseModel):
    client_id: str
    client_secret: str
    period_days: int = 30

class ImwebCredentials(BaseModel):
    api_key: str
    secret_key: str
    period_days: int = 30

class CombinedCredentials(BaseModel):
    naver: Optional[NaverCredentials] = None
    imweb: Optional[ImwebCredentials] = None


# ─────────────────────────────────────────
# 네이버 스마트스토어 API
# ─────────────────────────────────────────

def naver_get_token(client_id: str, client_secret: str) -> str:
    """네이버 커머스 API 액세스 토큰 발급"""
    timestamp = str(int(time.time() * 1000))
    password = f"{client_id}_{timestamp}"
    hashed = hmac.new(
        client_secret.encode("utf-8"),
        password.encode("utf-8"),
        hashlib.sha256
    ).digest()
    signature = base64.b64encode(hashed).decode("utf-8")

    url = "https://api.commerce.naver.com/external/v1/oauth2/token"
    payload = "&".join([
        f"client_id={client_id}",
        f"timestamp={timestamp}",
        f"client_secret_sign={signature}",
        "grant_type=client_credentials",
        "type=SELF",
    ])
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }
    resp = httpx.post(url, content=payload.encode("utf-8"), headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()["access_token"]


async def fetch_naver_orders(creds: NaverCredentials) -> list:
    """네이버 미발송 주문 조회 (결제완료, 상품준비중)"""
    token = naver_get_token(creds.client_id, creds.client_secret)
    headers = {"Authorization": f"Bearer {token}"}

    since = (datetime.now() - timedelta(days=creds.period_days)).strftime("%Y-%m-%dT00:00:00.000Z")
    until = datetime.now().strftime("%Y-%m-%dT23:59:59.999Z")

    # 미발송 상태 코드
    statuses = ["PAYMENT_DONE", "PREPARING_PRODUCT"]
    all_orders = []

    async with httpx.AsyncClient(timeout=15) as client:
        for status in statuses:
            page = 1
            while True:
                url = "https://api.commerce.naver.com/external/v1/pay-order/seller/orders/query-order-status"
                params = {
                    "orderStatusType": status,
                    "fromDate": since,
                    "toDate": until,
                    "page": page,
                    "pageSize": 300,
                }
                resp = await client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
                orders = data.get("contents", [])
                all_orders.extend(orders)
                if len(orders) < 300:
                    break
                page += 1

    return all_orders


def aggregate_naver(orders: list) -> list:
    """네이버 주문 → 상품별 수량 집계"""
    counter = defaultdict(lambda: {"name": "", "option": "", "qty": 0, "channel": "naver"})

    for order in orders:
        for item in order.get("productOrderList", []):
            product_name = item.get("productName", "")
            option = item.get("optionName", "") or item.get("singleOptionContent", "") or "-"
            qty = item.get("quantity", 1)
            key = f"{product_name}___{option}"
            counter[key]["name"] = product_name
            counter[key]["option"] = option
            counter[key]["qty"] += qty

    return list(counter.values())


# ─────────────────────────────────────────
# 아임웹 API
# ─────────────────────────────────────────

async def fetch_imweb_token(api_key: str, secret_key: str) -> str:
    """아임웹 액세스 토큰 발급"""
    url = "https://api.imweb.me/v2/auth"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={"key": api_key, "secret": secret_key})
        resp.raise_for_status()
        return resp.json()["data"]["access_token"]


async def fetch_imweb_orders(creds: ImwebCredentials) -> list:
    """아임웹 미발송 주문 조회 (order_confirm, ready_delivery)"""
    token = await fetch_imweb_token(creds.api_key, creds.secret_key)
    headers = {"access-token": token}

    since = (datetime.now() - timedelta(days=creds.period_days)).strftime("%Y%m%d")
    until = datetime.now().strftime("%Y%m%d")

    # 미발송 상태
    statuses = ["order_confirm", "ready_delivery"]
    all_orders = []

    async with httpx.AsyncClient(timeout=15) as client:
        for status in statuses:
            page = 1
            while True:
                url = "https://api.imweb.me/v2/shop/orders"
                params = {
                    "order_status": status,
                    "start_date": since,
                    "end_date": until,
                    "page": page,
                    "limit": 100,
                }
                resp = await client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
                orders = data.get("data", {}).get("list", [])
                all_orders.extend(orders)
                total_count = data.get("data", {}).get("total_count", 0)
                if len(all_orders) >= total_count:
                    break
                page += 1

    return all_orders


def aggregate_imweb(orders: list) -> list:
    """아임웹 주문 → 상품별 수량 집계"""
    counter = defaultdict(lambda: {"name": "", "option": "", "qty": 0, "channel": "imweb"})

    for order in orders:
        for item in order.get("order_item_list", []):
            product_name = item.get("prod_name", "")
            option_parts = []
            for opt in item.get("options", []):
                val = opt.get("value", "")
                if val:
                    option_parts.append(val)
            option = " / ".join(option_parts) if option_parts else "-"
            qty = item.get("ea", 1)
            key = f"{product_name}___{option}"
            counter[key]["name"] = product_name
            counter[key]["option"] = option
            counter[key]["qty"] += qty

    return list(counter.values())


# ─────────────────────────────────────────
# 결합 집계
# ─────────────────────────────────────────

def merge_results(naver_items: list, imweb_items: list) -> list:
    """두 채널 결과 병합 — 동일 상품명+옵션이면 합산"""
    combined = defaultdict(lambda: {"name": "", "option": "", "qty": 0, "channel": ""})

    for item in naver_items:
        key = f"{item['name']}___{item['option']}"
        combined[key]["name"] = item["name"]
        combined[key]["option"] = item["option"]
        combined[key]["qty"] += item["qty"]
        combined[key]["channel"] = "naver"

    for item in imweb_items:
        key = f"{item['name']}___{item['option']}"
        if combined[key]["channel"] == "naver":
            combined[key]["channel"] = "both"
        else:
            combined[key]["channel"] = "imweb"
        combined[key]["name"] = item["name"]
        combined[key]["option"] = item["option"]
        combined[key]["qty"] += item["qty"]

    result = sorted(combined.values(), key=lambda x: x["qty"], reverse=True)
    return result


# ─────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────

@app.post("/api/orders")
async def get_orders(creds: CombinedCredentials):
    naver_items = []
    imweb_items = []
    errors = []

    if creds.naver:
        try:
            raw = await fetch_naver_orders(creds.naver)
            naver_items = aggregate_naver(raw)
        except Exception as e:
            errors.append(f"네이버 오류: {str(e)}")

    if creds.imweb:
        try:
            raw = await fetch_imweb_orders(creds.imweb)
            imweb_items = aggregate_imweb(raw)
        except Exception as e:
            errors.append(f"아임웹 오류: {str(e)}")

    if not naver_items and not imweb_items and errors:
        raise HTTPException(status_code=400, detail=" | ".join(errors))

    merged = merge_results(naver_items, imweb_items)
    total_qty = sum(i["qty"] for i in merged)
    total_orders_approx = len(set(
        [f"n_{i}" for i in range(len(naver_items))] +
        [f"i_{i}" for i in range(len(imweb_items))]
    ))

    return {
        "items": merged,
        "summary": {
            "total_qty": total_qty,
            "total_items": len(merged),
            "naver_count": len(naver_items),
            "imweb_count": len(imweb_items),
        },
        "errors": errors,
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


# 정적 파일 (프론트엔드)
if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
