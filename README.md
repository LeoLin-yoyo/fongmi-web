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

### 网盘解析（Pan）
- 粘贴分享链接即解析：**10 平台全接入** —— 夸克 / UC / 迅雷 / 百度 / 139 / 123 / 115 / 光鸭 / 蓝奏云 / 蓝奏优享版
- 自动识别提取码（链接参数或文案「提取码：xxxx」），夸克 / UC / 迅雷 / 139 / 光鸭 / 蓝奏系支持游客（未登录）直接播放
- 目录浏览 + 面包屑，文件一键**在线播放**或**加入下载**
- 账号凭证粘贴登录，AES-256-GCM 加密落库；登录态校验与昵称回显
- 各平台私有协议完整移植：115 电脑端 RSA+XOR、123 CRC32 签名、139 AES-CBC + mcloud-sign、蓝奏 acw_sc__v2

### 下载（Download）
- 统一下载引擎：Range 分片并发 + `.part` 断点续传，一字节不浪费
- 暂停 / 继续 / 取消，重启后自动续传中断任务
- 下载目录可自定义；完成后自动并入「本地视频」片库（若目录已托管）
- SSE 实时进度 / 速度推送

### Telegram（TG）
- 粘贴 t.me 链接解析频道/群组消息，浏览文件清单
- 在线播放：流式代理（1MiB 块 LRU + 多连接预取），不需要等下完
- 一键加入下载队列（复用统一下载引擎）
- 网页内完成登录：扫码 / 手机号验证码 / 两步验证，登录态跨重启有效
- tdl 二进制自动下载（GitHub Releases，白名单校验）；全局串行队列（tdl bolt 单写者）

### 资源索引 · 聚合搜索
- 把 TG 频道 / 网盘分享目录建成可搜索的本地索引（片名自动清洗、去重）
- 聚合搜索一次跑遍「点播站点 + 我的 TG 频道 + 我的网盘资源」，虚拟源以独立 Tab 呈现
- 点击资源结果进入资源详情页，直接在线播放或加入下载

### 抖音解析（Douyin）
- 粘贴分享链接或整段分享文案，自动提取作品并解析
- **无水印**视频直链（`playwm` → `play`），支持图集原图批量下载
- 视频可在页面内直接播放；封面、背景音乐可单独下载
- 可选「风控 Cookie」：遇到页面无数据时粘贴浏览器 Cookie 提高成功率
- 复用统一下载引擎（分片并发 + 断点续传），下载完成自动进片库

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

### 登录管控
- 配置文件驱动：在 `data/auth.json` 填写账号密码即开启，账号或密码留空（或文件不存在）则保持免登录
- 开启后所有页面与接口都需登录；API 返回 401，页面自动跳转登录页
- HttpOnly Cookie 会话（HMAC 签名，12 小时有效），登录失败按 IP 限速
- 设置页可一键开启 / 关闭 / 退出登录；配置改动即时生效，无需重启

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
│  首页/分类  聚合搜索  详情播放  IPTV直播  网盘解析  Telegram  下载  本地 │
│        DPlayer · hls.js / flv.js · Canvas 弹幕 · srt/vtt 字幕           │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ REST /api/*
┌────────────────────────────────▼────────────────────────────────────────┐
│                FastAPI 后端（uvicorn · SQLite · httpx）                  │
│                                                                        │
│  VOD点播   IPTV直播   本地媒体   收藏/历史   埋点   网盘解析   Telegram  │
│     │         │          │                        │          │         │
│     │         │          │                    pan/（10平台）  tg/（tdl） │
│     │         │          │                        │          │         │
│     └─────────┴────┬─────┴────────┬───────────────┴──────────┘         │
│              Spider 爬虫引擎   downloader 下载引擎   resource_search    │
│         ├─ Type=1 HTTP API      Range 分片并发       TG/网盘资源索引     │
│         └─ Type=0 JS 爬虫       + 断点续传           → 聚合搜索虚拟源    │
└───────────────┬───────────────────────────┬────────────────────────────┘
                ▼                           ▼
         本地磁盘视频                订阅站点 / 直播源 / EPG / 网盘 / TG
```

技术栈：FastAPI + SQLAlchemy(异步 SQLite) + httpx 后端，Vue 3 + Vite + Pinia + TypeScript 前端，AES-128-CBC 解密兼容 FongMi 协议。网盘/TG 直链由服务端签发（凭证 AES-256-GCM 加密落库），下载引擎走 Range 分片并发 + `.part` 断点续传。

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
│   ├── downloads.py        #   统一下载任务（暂停/续传/SSE 进度）
│   ├── resources.py        #   资源索引（TG/网盘 → 可搜索）
│   └── tests/              #   pytest
├── pan/                    # 网盘解析（分享链接 → 直链 → 播放/下载）
│   ├── link.py             #   10 平台分享链接识别 + 提取码
│   ├── platforms/          #   各平台 API 客户端（quark / uc / …）
│   ├── resolver.py         #   会话缓存 + 直链签发（token 化，防 SSRF）
│   ├── accounts.py         #   账号 Cookie 管理（AES-GCM 加密落库）
│   ├── crypto.py           #   凭证加密
│   └── tests/              #   pytest
├── tg/                     # Telegram 模块（tdl 包壳）
│   ├── link.py             #   t.me 链接净化与解析
│   ├── runner.py           #   tdl 执行器：串行队列 + 进度解析
│   ├── login.py            #   交互登录状态机（PTY）
│   ├── session.py          #   会话/聊天列表
│   ├── serve.py            #   tdl serve 会话 + 文件清单
│   ├── stream.py           #   在线播放流式代理（块缓存 + 预取）
│   ├── tdlfetch.py         #   tdl 二进制自动下载
│   └── tests/              #   pytest
├── resource_search/        # 资源索引（TG 频道 / 网盘目录 → 可搜索）
│   ├── store.py            #   索引存储（片名清洗 + 去重）
│   ├── indexer.py          #   索引编排 + 聚合搜索虚拟源
│   └── tests/              #   pytest
├── auth/                   # 登录管控（配置文件驱动）
│   ├── core.py             #   配置读取 + 会话令牌 + 限速 + 路径判定
│   ├── api.py              #   登录/登出/状态/配置 接口
│   └── tests/              #   pytest
├── douyin/                 # 抖音解析（无水印视频 / 图集）
│   ├── link.py             #   分享链接识别与作品 ID 提取
│   ├── parser.py           #   分享页 JSON 提取 + 作品解析
│   ├── resolver.py         #   解析编排 + 直链签发
│   ├── api.py              #   解析/媒体代理/下载 接口
│   └── tests/              #   pytest
├── downloader/             # 统一下载引擎（TG / 网盘 / 直链共用）
│   ├── engine.py           #   Range 分片并发 + 断点续传
│   ├── journal.py          #   .part sidecar 断点记录
│   ├── tasks.py            #   任务状态机 + 速度 EMA + SSE
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
pytest api/tests local_video/tests pan/tests tg/tests douyin/tests downloader/tests resource_search/tests auth/tests

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
<summary><b>Telegram 功能需要什么？</b></summary>

需要一个 `tdl` 可执行文件（[iyear/tdl](https://github.com/iyear/tdl)）。可在「设置 → Telegram」或 TG 页点「自动下载 tdl」，程序会从 GitHub Releases 拉取对应平台的二进制到项目 `tdl/` 目录。另外 TG 通常需要代理，在设置里配好代理即可。
</details>

<details>
<summary><b>网盘账号怎么登录？</b></summary>

在「设置 → 网盘与下载」或「网盘」页点对应平台的「登录」，粘贴浏览器 Cookie（F12 → 网络 → 任意请求 → 复制 Cookie 请求头）。凭证以 AES-256-GCM 加密保存在本机。夸克 / UC / 迅雷 / 139 / 光鸭 / 蓝奏系未登录也能解析播放，其余平台下载需登录。
</details>

<details>
<summary><b>下载的文件在哪里？</b></summary>

默认在项目 `data/downloads/`，可在「设置 → 网盘与下载」改成任意绝对路径。若该目录已加入「本地视频」媒体目录，下载完成后会自动并入片库。
</details>

<details>
<summary><b>怎么开启登录，防止别人看到我的视频？</b></summary>

两种方式（二选一）：

1. **配置文件**：在项目根目录建 `data/auth.json`（可复制 `auth.json.example`），填入账号密码：
   ```json
   { "username": "admin", "password": "你的密码" }
   ```
2. **设置页**：打开「设置 → 登录管控」，填账号密码后点保存。

保存后立即生效，所有页面与接口都需要登录。**账号或密码留空（或删掉 `data/auth.json`）即关闭登录**，程序恢复免登录。密码以明文存于该文件（本机文件，请自行保管好权限）。
</details>

<details>
<summary><b>忘记登录密码了怎么办？</b></summary>

直接编辑 `data/auth.json` 改成新密码（或把账号密码清空以临时关闭登录），保存后立即生效，无需重启。
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
- [x] 网盘解析（10 平台）+ 统一下载引擎（分片断点续传）
- [x] Telegram 解析/在线播放/下载（tdl 包壳）
- [x] 资源索引 + 聚合搜索虚拟源（TG/网盘）
- [x] 登录管控（配置文件驱动，账号密码可留空关闭）
- [x] 抖音无水印解析（视频 / 图集）
- [ ] Tauri 桌面壳打包（可选）
- [ ] 弹幕在线匹配
- [ ] 多语言界面

## ⚠️ 免责声明

本项目仅供个人学习与技术研究，是一个不提供任何内容的播放器框架。不存储、不转载、不传播任何视频资源；所有站点与直播源均由使用者自行配置。使用本项目产生的一切后果由使用者自行承担，请遵守所在地区法律法规。

## 📄 License

[MIT](LICENSE)

