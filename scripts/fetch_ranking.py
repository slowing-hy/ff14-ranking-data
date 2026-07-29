#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FF14 国服水晶冲突榜单采集脚本（GitHub Actions 用）"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

# ============ 配置区 ============
# 当前赛季接口（无 season_id 参数）
CURRENT_API_URL = "https://ff14act.web.sdo.com/api/crystallineConflict/getSoloCurrentRanking2025"
# 历史赛季接口模板（需 season_id 参数）
HISTORY_API_URL_TEMPLATE = "https://ff14act.web.sdo.com/api/crystallineConflict/getSoloRanking2025?season_id={season_id}"

# 请求头
API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (FF14CrystalConflictTracker/1.0)",
    "Referer": "https://ff.web.sdo.com/",
    "Accept": "application/json",
}

REPO_ROOT = Path(__file__).resolve().parent.parent
SEASONS_FILE = REPO_ROOT / "seasons.json"
DATA_DIR = REPO_ROOT / "data"
CN_TZ = timezone(timedelta(hours=8))


def main() -> int:
    # 使用北京时区判断"今天"
    now_cn = datetime.now(CN_TZ)
    today = now_cn.strftime("%Y-%m-%d")
    print(f"[INFO] 当前北京时间: {now_cn.isoformat()}")
    print(f"[INFO] 本次采集日期: {today}")

    # 1. 读取赛季配置
    seasons_cfg = load_seasons()
    season = resolve_season(seasons_cfg, today)
    if season is None:
        print(f"[WARN] 日期 {today} 不在任何赛季范围内，跳过采集", file=sys.stderr)
        return 0

    season_id = season["id"]
    season_api_id = season.get("api_season_id", season_id.lstrip("s"))
    print(f"[INFO] 所属赛季: {season['name']} ({season_id}, api_id={season_api_id})")

    # 2. 判断调用当前接口还是历史接口
    current_season_id = seasons_cfg.get("current", "")
    if season_id == current_season_id:
        api_url = CURRENT_API_URL
        print(f"[INFO] 使用当前赛季接口: {api_url}")
    else:
        api_url = HISTORY_API_URL_TEMPLATE.format(season_id=season_api_id)
        print(f"[INFO] 使用历史赛季接口: {api_url}")

    # 3. 调用榜单接口
    try:
        raw = fetch_raw_ranking(api_url)
    except Exception as e:
        print(f"[ERROR] 拉取接口失败: {e}", file=sys.stderr)
        return 3

    # 4. 解析为统一格式
    rankings = parse_official_response(raw)
    if not rankings:
        print("[WARN] 解析后排名列表为空，跳过写入", file=sys.stderr)
        return 0

    print(f"[INFO] 采集到 {len(rankings)} 条排名记录")

    # 5. 写入 data/{season}/{date}.json
    out_dir = DATA_DIR / season_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{today}.json"

    payload = {
        "date": today,
        "season": season_id,
        "fetched_at": now_cn.isoformat(timespec="seconds"),
        "rankings": rankings,
    }

    with out_file.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[OK] 已写入 {out_file.relative_to(REPO_ROOT)}")
    return 0


def load_seasons() -> dict:
    if not SEASONS_FILE.exists():
        raise FileNotFoundError(f"未找到 seasons.json: {SEASONS_FILE}")
    with SEASONS_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_season(seasons_cfg: dict, date_str: str):
    """根据 YYYY-MM-DD 日期返回所属赛季 dict，无匹配返回 None。"""
    for s in seasons_cfg.get("seasons", []):
        start = s.get("start_date")
        end = s.get("end_date")
        if start and end and start <= date_str <= end:
            return s
    # 兜底：使用 current 标记
    current_id = seasons_cfg.get("current")
    if current_id:
        for s in seasons_cfg.get("seasons", []):
            if s.get("id") == current_id:
                return s
    return None


def fetch_raw_ranking(url: str) -> dict:
    """调用 FF14 国服榜单接口，返回原始 JSON 字典。"""
    print(f"[INFO] GET {url}")
    resp = requests.get(url, headers=API_HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # 接口返回 { code: 1, data: { list: [...] } }
    if data.get("code") != 1:
        print(f"[WARN] API code={data.get('code')}, msg={data.get('msg', '')}", file=sys.stderr)
    return data


def parse_official_response(raw: dict) -> list:
    """
    适配 FF14 国服水晶冲突接口字段：
      character_name      -> player_name
      area_name           -> server（大区：陆行鸟/莫古力/猫小胖）
      pvp_order           -> rank（官方排名）
      colosseumsolorankwincount   -> wins
      colosseumsolorankmatchcount -> total_matches
      colosseumsolorankmatchrate  -> win_rate（百分比，需 /100）
      colosseumsolomatchtier      -> tier（段位类型）
      colosseumsolomatchrank      -> 段位等级
      colosseumsolomatchvictorymark -> stars（连胜标记）
    """
    api_data = raw.get("data", {})
    if not isinstance(api_data, dict):
        print(f"[WARN] data 字段不是 dict", file=sys.stderr)
        return []

    candidates = api_data.get("list")
    if not isinstance(candidates, list):
        print(f"[WARN] data.list 不存在或不是 list, keys={list(api_data.keys())}", file=sys.stderr)
        return []

    items = []
    for idx, row in enumerate(candidates, start=1):
        wins = _to_int(row.get("colosseumsolorankwincount"))
        total = _to_int(row.get("colosseumsolorankmatchcount"))
        match_rate = _to_float(row.get("colosseumsolorankmatchrate"))

        # 自动补全
        losses = None
        if wins is not None and total is not None:
            losses = total - wins
        win_rate = None
        if match_rate is not None:
            win_rate = round(match_rate / 100.0, 4)

        items.append({
            "rank": _to_int(row.get("pvp_order")) or idx,
            "player_name": str(row.get("character_name") or "未知"),
            "server": str(row.get("area_name") or "未知"),
            "rating": None,  # 该接口无 rating 字段
            "wins": wins,
            "losses": losses,
            "total_matches": total,
            "win_rate": win_rate,
            "tier": _to_int(row.get("colosseumsolomatchtier")),
            "sub_tier": None,  # 接口未提供
            "stars": _to_int(row.get("colosseumsolomatchvictorymark")),
            "score_within_tier": None,  # 接口未提供
        })

    return items


def _to_int(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _to_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    sys.exit(main())
