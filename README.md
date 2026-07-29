# FF14 水晶冲突榜单数据仓库

本仓库由 [FF14CrystalConflictTracker](../FF14CrystalConflictTracker) 客户端读取，存储每日榜单快照。

## 目录结构

```
ff14-ranking-data/
├── .github/
│   └── workflows/
│       └── fetch-ranking.yml     # GitHub Actions 定时采集
├── scripts/
│   └── fetch_ranking.py          # Python 采集脚本
├── data/
│   └── s14/
│       └── 2026-07-28.json       # 每日榜单快照
├── seasons.json                  # 赛季配置
└── README.md
```

## 使用步骤

1. 在 GitHub 创建公开仓库（建议命名 `ff14-ranking-data`），将本目录所有文件推送上去。
2. 在仓库 `Settings → Secrets and variables → Actions` 中添加：
   - `FF14_API_URL`：FF14 国服水晶冲突榜单接口地址
   - `FF14_API_PARAMS`（可选）：JSON 字符串形式的请求参数，例如 `{"season": 14, "page": 1}`
3. 赛季切换时手动修改 `seasons.json`。
4. 客户端 `appsettings.json` 中的 `DataSource.RepositoryUrl` 指向本仓库 Raw URL 前缀：
   `https://raw.githubusercontent.com/<你的用户名>/ff14-ranking-data/main`

## 采集时机

- 中国时间每天 17:00 榜单更新
- GitHub Actions cron `30 9 * * *`（UTC 09:30 = 中国 17:30）自动触发
- 支持在 Actions 页面手动 `workflow_dispatch` 触发

## 接口适配

`scripts/fetch_ranking.py` 中的 `parse_official_response(raw)` 是适配函数。
接口响应结构不同时，仅需调整该函数的字段映射，其余逻辑无需改动。
