<div align="center">

# 🎬 FongMi TV Web

**把 FongMi TV 装进浏览器 —— 一份订阅，全设备畅看**

FastAPI × Vue 3 全栈实现 · 点播聚合 · IPTV 直播 · 弹幕字幕 · 本地媒体库

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Node.js](https://img.shields.io/badge/Node.js-18+-339933?logo=node.js&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)
![Vue 3](https://img.shields.io/badge/Vue-3.5-4FC08D?logo=vue.js&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow)

[快速开始](#-快速开始) · [功能全景](#-功能全景) · [架构设计](#-架构设计) · [JS 爬虫引擎](#️-js-爬虫引擎) · [FAQ](#-faq)

</div>

---

一个将 [FongMi TV](https://github.com/FongMi/Release)（Android 端电视聚合播放器）的配置生态与核心体验移植到 Web 的全栈项目。不装 App、不折腾盒子 —— 浏览器打开即用，Windows / macOS / Linux 全平台通吃，还能通过局域网共享给电视和手机。

手机上那套已经调好的订阅，复制一个链接过来，站点、直播源原样照搬。

## ✨ 项目特色

- 🔌 **无缝兼容 FongMi 生态** — 直接导入 FongMi TV 订阅链接，AES-128-CBC 加密配置自动解密；多个订阅一起导入，站点自动合并去重
- 🕷️ **双引擎爬虫架构** — HTTP API 站点（Type=1）直连秒搜；JS 爬虫（Type=0）内嵌 QuickJS 沙箱执行，Node.js 常驻进程兜底，FongMi 系 JS 站点照样跑
- 🔍 **真·聚合搜索** — 一次搜索并发跑遍订阅中全部站点，结果去重、封面自动补全，还带拼音首字母模糊索引
- 🎬 **播放器全家桶** — HLS / FLV / MP4 全格式，Canvas 弹幕（兼容 B 站 XML），外挂 srt/vtt 字幕 + 内嵌字幕轨，倍速播放
- 🖥️ **真·跨平台** — 没有 Electron 那几百 MB 的壳，一个 Python 进程 + 静态页面，Raspberry Pi 都跑得动
- 🧪 **认真做工程** — pytest + Vitest + Playwright 三层测试，文档驱动开发，每个功能都有需求文档与开发记录留档

## 📦 功能全景

### 点播（VOD）
- 多站点聚合搜索、分类浏览、详情页选集播放
- 收藏夹 + 观看历史，跨会话保存进度，看到哪接着看
- 封面图片代理：没有 CORS 头的站点也能正常显示封面
- 卡片新标签页打开，浏览不丢上下文

### 直播（IPTV）
- M3U / TXT 直播源自动解析，同名频道多线路自动合并
- EPG 电子节目单
- 频道级 **代理 / 直连** 一键切换，卡顿源不再干瞪眼
- 分组折叠、频道搜索

### 播放器
- hls.js + flv.js 双内核，覆盖主流流媒体格式
- 弹幕：Canvas 渲染，透明度 / 速度 / 显示区域可调，支持导入 B 站格式 `.xml` / `.txt` 弹幕文件
- 字幕：内嵌字幕轨选择 + 外挂 `.srt` / `.vtt` 导入，字号可调
- 倍速播放、上/下集无缝切换
- 实时显示分辨率、缓冲进度、下载速度

### 本地媒体库
- 扫描本机视频目录，ffprobe 自动提取元数据并生成缩略图
- HTTP Range 流式播放，拖动进度条秒响应
- 与收藏 / 历史体系打通

### 工程与体验
- 多订阅管理：多个配置链接同时生效，站点合并去重
- 内置播放代理：受 Referer / 跨域限制的流也能播
- 本地埋点看板：播放指标（含 P95 分位数）本地聚合，数据不出本机
- 局域网共享：`0.0.0.0` 监听，电视 / 手机 / 平板直接访问 `http://<你的IP>:8000`
- 中文界面 · 暗色主题

> 🖼️ 截图位（欢迎补充）：把运行截图放进 `docs/screenshots/` 后取消注释
>
> <!--
> ![首页](docs/screenshots/home.png)
> ![播放页](docs/screenshots/play.png)
> ![直播](docs/screenshots/live.png)
> -->

## 🚀 快速开始

### 前置依赖

- Python 3.10+
- Node.js 18+（构建前端；如订阅含 JS 爬虫站点，运行时也会用到）

### 安装运行

```bash
git clone https://github.com/LeoLin-yoyo/fongmi-web.git
cd fongmi-web

# 1. 后端依赖
pip install -r requirements.txt

# 2. 构建前端（仅首次）
cd frontend
npm install
npm run build
cd ..

# 3. 启动（局域网可访问）
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

或者用一键脚本 —— Windows 双击 [`start.bat`](start.bat)，macOS / Linux 运行 `./start.sh`（会自动检测并构建前端）。

浏览器打开 **http://localhost:8000**，进入 **设置** 页粘贴你的 FongMi 订阅链接，导入完成即可开看。

### 局域网共享

服务监听 `0.0.0.0:8000`，同一 Wi-Fi 下的电视 / 手机浏览器直接访问 `http://<你的局域网IP>:8000`。首次运行如系统弹防火墙提示，选择「允许访问」即可。

## 🏗️ 架构设计

```
┌───────────────────── 浏览器（Vue 3 + Naive UI SPA）─────────────────────┐
│   首页 / 分类   聚合搜索   详情播放   IPTV 直播   本地媒体   设置中心      │
│        DPlayer · hls.js / flv.js · Canvas 弹幕 · srt/vtt 字幕           │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ REST /api/*
┌────────────────────────────────▼────────────────────────────────────────┐
│                FastAPI 后端（uvicorn · SQLite · httpx）                  │
│                                                                        │
│   VOD 点播      IPTV 直播      本地媒体库     收藏/历史     埋点指标      │
│      │             │               │                                  │
│      └─────────────┴───────┬───────┘                                  │
│                   Spider 爬虫引擎                                     │
│            ├─ Type=1  HTTP API 站点（直连）                             │
│            └─ Type=0  JS 爬虫                                          │
│                 ├─ QuickJS 沙箱（进程内，全局串行锁）                    │
│                 └─ Node.js 常驻进程（兜底运行时）                       │
└───────────────┬───────────────────────────┬────────────────────────────┘
                ▼                           ▼
         本地磁盘视频                订阅站点 / 直播源 / EPG
```

技术栈：FastAPI + SQLAlchemy(异步 SQLite) + httpx 后端，Vue 3 + Vite + Pinia + TypeScript 前端，AES-128-CBC 解密兼容 FongMi 协议。

## 🕷️ JS 爬虫引擎

FongMi 生态里大量站点是 JS 爬虫（`spider` 字段直接是一段 JS 代码）。本项目为此做了双层运行时：

1. **QuickJS 沙箱（默认）** — 通过 Python 绑定在进程内执行，轻量、启动零开销；
2. **Node.js 兜底** — QuickJS 环境差异导致站点跑不通时，自动回落到 `node_engine.cjs` 常驻子进程。

一个值得说的工程细节：QuickJS 的 C 层状态是进程级共享且非线程安全的，并发生命周期会直接 `abort` 整个后端。引擎因此用**全局串行锁**把所有 JS 执行串行化 —— 宁可排队等一拍，绝不带崩一个进程。这是聚合器产品的稳定性底线。

## 📂 项目结构

```
fongmi-web/
├── main.py                 # FastAPI 入口（SPA 静态托管 + 全局异常处理）
├── api/                    # REST 路由
│   ├── vod.py              #   点播：分类/详情/播放
│   ├── live.py             #   直播：频道分组/EPG
│   ├── live_source.py      #   M3U/TXT 直播源解析
│   ├── decoder.py          #   FongMi 配置解密（AES-128-CBC）
│   ├── player.py           #   播放代理（跨域流转发）
│   ├── image.py            #   封面图片代理
│   ├── history.py          #   收藏/历史 CRUD
│   ├── metrics.py          #   本地埋点聚合（P95 分位）
│   └── tests/              #   pytest
├── spider/                 # 爬虫引擎
│   ├── engine.py           #   调度：按站点类型分发 + LRU 缓存
│   ├── js_runtime.py       #   QuickJS 沙箱运行时
│   ├── node_runtime.py     #   Node.js 常驻进程兜底
│   ├── http_spider.py      #   Type=1 HTTP API 站点
│   ├── search.py           #   多站点并发聚合搜索
│   └── pinyin_index.py     #   拼音模糊索引
├── local_video/            # 本地媒体库
│   ├── scanner.py          #   目录扫描
│   ├── probe.py            #   ffprobe 元数据/缩略图
│   ├── streaming.py        #   HTTP Range 流式播放
│   └── tests/              #   pytest
├── model/                  # SQLAlchemy ORM + Pydantic 模型
├── frontend/               # Vue 3 SPA
│   ├── e2e/                #   Playwright 端到端测试
│   └── src/
│       ├── views/          #   页面组件
│       ├── composables/    #   usePlayer / useDanmaku
│       ├── stores/         #   Pinia 状态
│       └── api/            #   HTTP 客户端
├── docs/                   # 设计文档（多订阅、开发指南等）
└── us/                     # 文档驱动开发：需求 → 路线图 → 开发记录 → 测试报告
```

## 🧪 开发与测试

```bash
# 后端单元测试
pytest api/tests local_video/tests

# 前端单元测试
cd frontend && npm run test

# 端到端测试
npx playwright test
```

项目采用**文档驱动开发**：每个功能先在 `us/` 立需求文档，开发后留开发记录与测试报告，`docs/` 存放专题设计（如[多链接订阅](docs/MULTI_SUBSCRIBE.md)、[开发指南](docs/DEVELOPMENT.md)）。PR 同样欢迎，附上改动说明与对应测试即可。

## ❓ FAQ

<details>
<summary><b>和 FongMi TV 原版是什么关系？</b></summary>

独立实现的 Web 端，不是官方项目。只兼容其订阅配置格式（AES-128-CBC 加密的站点/直播源配置），让已有订阅在浏览器里继续发挥作用。
</details>

<details>
<summary><b>项目里有内置的站点或源吗？</b></summary>

没有。本项目只是一个播放器框架，不提供、不存储任何内容，所有站点与直播源均来自你自己导入的订阅。
</details>

<details>
<summary><b>JS 站点搜索没反应？</b></summary>

JS 爬虫需要 Python 包 `quickjs`（已在 requirements.txt 中）或系统安装的 Node.js。若两者都不可用，引擎会跳过 JS 站点，HTTP API 站点不受影响。
</details>

<details>
<summary><b>端口被占用 / 想换端口？</b></summary>

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 9000
```
</details>

## 🗺️ 路线图

- [x] 多订阅导入与站点合并去重
- [x] 本地媒体库 + 缩略图
- [x] 直播 EPG 与代理/直连切换
- [ ] Tauri 桌面壳打包（可选）
- [ ] 弹幕在线匹配
- [ ] 多语言界面

## ⚠️ 免责声明

本项目仅供个人学习与技术研究，是一个不提供任何内容的播放器框架。不存储、不转载、不传播任何视频资源；所有站点与直播源均由使用者自行配置。使用本项目产生的一切后果由使用者自行承担，请遵守所在地区法律法规。

## 📄 License

[MIT](LICENSE)

