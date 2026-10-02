# FongMi TV Web

将 FongMi TV (Android 视频聚合器) 转换为桌面 Web 应用，支持 Windows / macOS / Linux。

## 功能

- **VOD 点播** — 多站点聚合搜索、分类浏览、剧集选择、hls.js 播放
- **IPTV 直播** — M3U/TXT 源解析、同名频道合并多线路、频道折叠/搜索
- **播放信息** — 实时分辨率显示、缓冲进度条、下载速度监控
- **聚合搜索** — 并行搜索 71+ 站点，结果去重、图片自动补全
- **收藏 & 历史** — 跨会话保存观看进度
- **自定义代理** — 可在 Settings 页面配置代理，不硬编码

## 快速开始

### 前置依赖

- Python 3.10+
- Node.js 18+

### 安装 & 运行

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 2. 安装前端依赖并构建
cd frontend
npm install
npm run build
cd ..

# 3. 启动服务
uvicorn main:app --host 127.0.0.1 --port 8000
```

浏览器打开 `http://localhost:8000`

### 导入配置

在 Settings 页面输入 FongMi 订阅 URL，系统会自动解密并导入站点和直播源。

## 技术栈

| 层 | 技术 |
|------|------|
| 后端 | Python FastAPI + uvicorn + SQLite + httpx |
| 前端 | Vue 3 + Vite + Naive UI + TypeScript |
| 播放器 | hls.js (HLS) + HTML5 Video |
| 解密 | AES-128-CBC (兼容 FongMi 协议) |

## 项目结构

```
fongmi-web/
├── main.py                 # FastAPI entry
├── api/                    # API routes
│   ├── vod.py              # VOD endpoints
│   ├── live.py             # Live TV endpoints
│   ├── live_source.py      # Live source fetching & parsing
│   ├── decoder.py          # Config decryption
│   ├── player.py           # Media proxy
│   ├── image.py            # Image proxy (CORS)
│   ├── history.py          # History & Keep CRUD
│   ├── metrics.py          # Runtime metrics
│   ├── system.py           # System config
│   └── tests/              # Backend tests (pytest)
├── local_video/            # Local video scan & streaming module
│   ├── scanner.py          # Filesystem scanner
│   ├── streaming.py        # Range-request streaming
│   └── tests/              # Module tests (pytest)
├── spider/                 # Data fetching engine
│   ├── http_spider.py      # Type=1 HTTP API spider
│   ├── search.py           # Multi-site search
│   ├── engine.py           # Spider dispatcher
│   └── proxy_config.py     # Proxy settings
├── model/                  # Data models
│   ├── database.py         # SQLAlchemy ORM
│   └── bean.py             # Pydantic schemas
├── data/                   # Runtime data (gitignored)
└── frontend/               # Vue 3 SPA
    ├── e2e/                # Playwright E2E tests
    └── src/
        ├── views/          # Page components
        ├── api/            # HTTP client
        ├── composables/    # Player / danmaku composables
        ├── stores/         # Reactive stores
        └── router/         # Vue Router
```

## License

MIT
