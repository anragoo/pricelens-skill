#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PriceLens 命令行客户端，用于搜索商品和获取购买链接。

Examples:
    python3 pricelens.py search --keyword "iPhone 17" --source jd
    python3 pricelens.py search --keyword "DDR5 6400 16G" --sort price
    python3 pricelens.py detail --id "<PriceLens item ID>"

Search results contain marketplace labels and PriceLens item IDs. Use an ID from
search results with detail before showing a purchase link. The client uses only
Python's standard library.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import sys
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation

API_URL = os.environ.get("PRICELENS_API_URL", "https://1zlheidou.cn/pricelens").rstrip("/")
API_TOKEN = os.environ.get("PRICELENS_API_TOKEN", "")
CLIENT_VERSION = "3.4.6"
TIMEOUT = 150
PUBLIC_SOURCES = {
    "jd": 2,
    "pdd": 3,
    "taobao": 1,
    "douyin": 7,
    "vip": 5,
    "kuaishou": 8,
}


def _generic_error() -> dict:
    return {"ok": False,
            "error": {"message": "PriceLens 服务暂时不可用，请稍后重试。"}}


def _price_bound(value: str) -> str:
    """Validate and normalize a nonnegative finite price for JSON transport."""
    if len(value) > 64:
        raise argparse.ArgumentTypeError("价格输入过长。")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("价格必须是有效数字。") from exc
    if not amount.is_finite():
        raise argparse.ArgumentTypeError("价格必须是有限数字。")
    if amount < 0:
        raise argparse.ArgumentTypeError("价格不能小于 0。")
    if amount.as_tuple().exponent < -6:
        raise argparse.ArgumentTypeError("价格最多支持 6 位小数。")
    if amount > Decimal("1000000000000"):
        raise argparse.ArgumentTypeError("价格超出支持范围。")
    if amount == 0:
        return "0"
    normalized = format(amount, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def call(path: str, payload: dict) -> dict:
    """POST 到服务端，返回解析好的 JSON。"""
    url = f"{API_URL}{path}"
    headers = {"Content-Type": "application/json; charset=utf-8",
               "Accept": "application/json",
               "User-Agent": f"pricelens-skill/{CLIENT_VERSION}"}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return _generic_error()

    try:
        obj = json.loads(raw)
    except ValueError:
        return _generic_error()
    if not isinstance(obj, dict):
        return _generic_error()
    if obj.get("ok") is False:
        return _generic_error()
    return obj


def _call_many(requests: list[tuple[str, dict]], max_workers: int) -> list[dict]:
    """Run independent PriceLens requests in parallel and keep their order."""
    with ThreadPoolExecutor(max_workers=min(max_workers, len(requests))) as pool:
        futures = [pool.submit(call, path, payload) for path, payload in requests]
        results = []
        for future in futures:
            try:
                results.append(future.result())
            except Exception:
                results.append(_generic_error())
    return results


def main() -> int:
    p = argparse.ArgumentParser(description="PriceLens —— 多平台商品查询")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("search", help="按关键词搜商品")
    ps.add_argument("--keyword", required=True)
    ps.add_argument("--source", choices=tuple(PUBLIC_SOURCES), nargs="+", required=True)
    ps.add_argument("--sort", choices=["price", "sales", "default"], default="default")
    ps.add_argument("--min-price", type=_price_bound, help="单件商品最低价")
    ps.add_argument("--max-price", type=_price_bound, help="单件商品最高价")
    pd = sub.add_parser("detail", help="获取商品详情和 PriceLens 购买链接")
    pd.add_argument("--id", nargs="+", required=True, help="搜索结果中的 PriceLens 商品 ID")

    args = p.parse_args()

    if args.cmd == "search":
        if (args.min_price is not None and args.max_price is not None
                and Decimal(args.min_price) > Decimal(args.max_price)):
            p.error("--min-price 不能大于 --max-price。")
        base_payload = {"keyword": args.keyword, "sort": args.sort}
        if args.min_price is not None:
            base_payload["min_price"] = args.min_price
        if args.max_price is not None:
            base_payload["max_price"] = args.max_price
        if len(args.source) == 1:
            payload = {**base_payload, "source": PUBLIC_SOURCES[args.source[0]]}
            out = call("/v1/search", payload)
        else:
            requests = [
                ("/v1/search", {**base_payload, "source": PUBLIC_SOURCES[source]})
                for source in args.source
            ]
            results = _call_many(requests, max_workers=6)
            out = {
                "ok": any(bool(result.get("ok")) for result in results),
                "service": "PriceLens",
                "results": [
                    {"platform": source, "result": result}
                    for source, result in zip(args.source, results)
                ],
            }
    else:
        if len(args.id) == 1:
            out = call("/v1/detail", {"id": args.id[0]})
        else:
            requests = [("/v1/detail", {"id": item_id}) for item_id in args.id]
            results = _call_many(requests, max_workers=4)
            out = {
                "ok": any(bool(result.get("ok")) for result in results),
                "service": "PriceLens",
                "results": [
                    {"id": item_id, "result": result}
                    for item_id, result in zip(args.id, results)
                ],
            }

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
