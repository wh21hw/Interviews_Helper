# Interviews Helper

[![tests](https://github.com/wh21hw/Interviews_Helper/actions/workflows/tests.yml/badge.svg)](https://github.com/wh21hw/Interviews_Helper/actions/workflows/tests.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Interviews Helper 是一个**面向 Agent 的个人面经库构建工具**。你只需要告诉 Agent 目标岗位，例如“后端开发工程师”或“大模型算法工程师”，Agent 就可以调用本项目完成公开资料采集、问题抽取、重复题合并、来源留证、离线建库和混合检索。

仓库只提供代码骨架和脱敏示例，不附带作者的面经数据、网页正文、OCR 图片、数据库、浏览器登录态或 Cookie。每位使用者在本机建立自己的题库。

## 1. 最终会得到什么

一次完整运行会生成三种互补的产物：

| 产物 | 默认位置 | 用途 |
| --- | --- | --- |
| 来源快照 | `data/interviews.json` | 人工审计、重新抽题和数据迁移 |
| 规范题库 | `data/interviews.sqlite3` | Agent 检索、程序查询和来源关联 |
| 可视化报告 | `interviews.html` | 浏览器筛选、查看题目与来源 |

每道题会尽量保留：

- 规范化题面和主题；
- 公司、岗位方向、平台和出现次数；
- 来源标题、公开 URL 和证据片段；
- 正文行号或 OCR 图片页码；
- 来源完整性、采集深度和质量分。

## 2. 当前支持范围

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 小红书关键词发现 | 已支持 | 使用用户手动登录后的真实 Chrome，保守低频访问 |
| 小红书多图 OCR | 已支持 | 按图片顺序下载到本机并使用 RapidOCR |
| 牛客正文采集 | 已支持 | 需要提供具体公开页面 URL |
| 知乎正文采集 | 已支持 | 需要提供具体问题、回答或文章 URL |
| 微信公众号正文采集 | 已支持 | 需要提供具体公开文章 URL |
| 普通文章页面 | 已支持 | 优先读取 `article` 或 `main` 正文容器 |
| 关键词断点续跑 | 已支持 | 按任务指纹恢复最近未完成运行 |
| URL 与笔记断点续跑 | 已支持 | 成功项不会重复访问，失败项保留原因 |
| grep + 向量召回 | 已支持 | 默认零模型下载，可选 Sentence Transformers |
| 自动生成面试答案 | 未内置 | 建议由上层 Agent 基于召回结果生成并单独保存 |
| 自动处理验证码 | 不支持 | 必须由用户本人在浏览器中处理 |

牛客、知乎和微信公众号目前没有站内关键词搜索器。推荐做法是让 Agent 或用户先整理公开 URL，再通过 `--url-file` 交给本项目读取。

## 3. 五分钟跑通脱敏示例

### 3.1 环境要求

- Python 3.9 或更高版本；
- Windows、macOS 或 Linux；
- 完整采集需要本机安装 Chrome、Chromium 或 Edge；
- 离线建库和检索不需要启动浏览器。

### 3.2 下载与安装

Windows PowerShell：

```powershell
git clone https://github.com/wh21hw/Interviews_Helper.git
cd Interviews_Helper

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

macOS / Linux：

```bash
git clone https://github.com/wh21hw/Interviews_Helper.git
cd Interviews_Helper

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

如果旧版 pip 在代理环境中无法创建 editable build，而环境中已经装有 setuptools，可以使用兼容入口：

```powershell
.\.venv\Scripts\python.exe setup.py develop
```

### 3.3 构建示例题库

Windows：

```powershell
.\.venv\Scripts\interviews-helper.exe build `
  --seed .\examples\seed_data.example.json
```

macOS / Linux：

```bash
interviews-helper build --seed ./examples/seed_data.example.json
```

命令最后会打印类似结果：

```json
{"sources": 1, "questions": 2, "database": ".../data/interviews.sqlite3", "html": ".../interviews.html"}
```

双击 `interviews.html` 即可查看本地报告。再试一次检索：

```powershell
.\.venv\Scripts\interviews-helper.exe search "缓存问题怎么解决" --top-k 5 --json
```

至此，安装、建库、HTML 和 Agent JSON 检索链路已经全部跑通。

## 4. 为自己的岗位建立题库

### 4.1 确定目标岗位

最小采集参数只有 `--job`：

```powershell
.\run.ps1 collect --job "后端开发工程师"
```

没有显式传入 `--keywords` 时，程序会自动生成：

```text
后端开发工程师 面经
后端开发工程师 一面
后端开发工程师 面试题
```

岗位比较宽泛时，建议明确给出关键词：

```powershell
.\run.ps1 collect `
  --job "大模型算法工程师" `
  --keywords "LLM算法 面经,大模型训练 面经,RAG 面试题" `
  --limit 3 `
  --delay 15
```

`--limit 3 --delay 15` 表示每个关键词最多处理 3 篇，并且页面操作至少间隔 15 秒。不要为了追求数量把间隔调得很短。

### 4.2 准备手动登录状态

推荐先逐个平台登录：

```powershell
.\run.ps1 login xhs --wait 600
.\run.ps1 login nowcoder --wait 600
.\run.ps1 login zhihu --wait 600
.\run.ps1 login weixin --wait 600
```

程序会打开独立浏览器窗口。请在窗口中自行扫码、登录或完成验证，然后关闭本次打开的登录标签页。登录状态分别保存在：

```text
.browser-profile-xhs-2/
.browser-profile-nowcoder/
.browser-profile-zhihu/
.browser-profile-weixin/
```

这些目录已被 `.gitignore` 排除。程序不会读取、打印或导出 Cookie，也不会自动填写账号密码。

### 4.3 补充牛客、知乎和公众号 URL

复制示例文件：

```powershell
Copy-Item .\examples\urls.example.txt .\public_urls.txt
```

在 `public_urls.txt` 中每行填写一个公开页面地址：

```text
# 注释行不会执行
https://www.nowcoder.com/discuss/你的页面
https://www.zhihu.com/question/你的页面
https://mp.weixin.qq.com/s/你的页面
```

随后运行：

```powershell
.\run.ps1 collect `
  --job "后端开发工程师" `
  --url-file .\public_urls.txt `
  --limit 3 `
  --delay 15
```

程序会按域名使用不同浏览器 Profile。某个平台失败不会删除已经落盘的来源，也不会阻止后续离线重建。

## 5. 中断后如何继续

每次 `collect` 都会创建：

```text
data/runs/<run-id>.json
```

状态中包含任务参数指纹、完成项、失败项、开始时间和更新时间。每次更新先写临时文件，再使用原子替换，进程被关闭时不容易留下半个 JSON。

查看最近任务：

```powershell
.\run.ps1 status
.\run.ps1 status --json
```

使用**完全相同的岗位、关键词、URL 和采集参数**再次执行时，程序会自动找到最近未完成任务：

```powershell
.\run.ps1 collect --job "后端开发工程师" --limit 3 --delay 15
```

也可以使用上次返回的 ID 精确恢复：

```powershell
.\run.ps1 collect `
  --job "后端开发工程师" `
  --run-id "20260914-120000-000000-a1b2c3d4"
```

如果确实要创建一项全新运行：

```powershell
.\run.ps1 collect --job "后端开发工程师" --no-resume
```

已完成的关键词、笔记和 URL 会被跳过；仍失败的项目保留在 `failures` 中，下一次可以继续处理。

## 6. 离线重建

采集到一半也可以重建当前题库：

```powershell
.\run.ps1 build
```

`build` 会合并：

1. `--seed` 指定的人工核验数据；
2. 已有的 `data/interviews.json`；
3. `data/raw/` 中逐篇立即落盘的原始快照。

然后重新执行问题抽取、规范化、相似题合并、SQLite 建库和 HTML 生成。修改抽题规则后不需要重新访问平台。

若想建立另一套完全隔离的题库，推荐为它设置独立目录：

```powershell
$env:INTERVIEWS_HELPER_HOME = "D:\interview-libraries\backend"
.\run.ps1 build --seed .\examples\seed_data.example.json
```

`INTERVIEWS_HELPER_HOME` 控制 `data/`、报告和浏览器 Profile 的根目录，适合 Agent 自动化任务使用。

## 7. grep 与向量混合召回

### 7.1 默认模式

```powershell
.\run.ps1 search "缓存穿透怎么处理" --top-k 10 --json
.\run.ps1 search "一致性" --grep "Redis|缓存" --top-k 10
```

默认检索包含两路：

1. **grep 路**：查询词重合、完整短语命中和可选正则命中；
2. **向量路**：把中文字符 2/3-gram 与英文技术词映射为本地 Feature Hashing 向量，再计算余弦相似度。

两路排名通过 Reciprocal Rank Fusion 合并。默认模式不下载模型、不请求外部 API，适合先从几千到几万道题中取出一个候选集。

返回结果包含：

```json
{
  "question": "Redis 缓存穿透怎么解决？",
  "topic": "数据库与缓存",
  "score": 0.0327,
  "recall": {"grep": 1.0, "vector": 0.71},
  "sources": [
    {"title": "来源标题", "url": "公开链接", "evidence_excerpt": "原文证据"}
  ]
}
```

### 7.2 可选稠密语义向量

需要更强语义召回时，额外安装 Sentence Transformers：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[vectors]"
```

使用模型名或本地模型路径：

```powershell
.\run.ps1 search "服务雪崩怎么处理" `
  --encoder sentence-transformers `
  --model "BAAI/bge-small-zh-v1.5" `
  --top-k 10 `
  --json
```

首次使用远程模型名可能下载较大文件。离线或隐私要求较高时，请传本地模型路径，或继续使用默认 `hashing` 编码器。

## 8. 交给 Agent 使用

可以把下面这段提示直接交给支持终端操作的 Agent：

```text
请使用当前仓库的 Interviews Helper 为“后端开发工程师”建立个人面经库。

1. 先阅读 AGENTS.md 和 README.md，不读取或输出任何 Cookie、浏览器 Profile。
2. 检查 interviews-helper 是否安装；未安装则执行 python -m pip install -e .。
3. 若缺少登录态，运行 interviews-helper login xhs，并等待我手动登录。
4. 使用 interviews-helper collect --job "后端开发工程师" --limit 3 --delay 15。
5. 中断时保留原参数续跑，不提高访问频率，不处理验证码。
6. 完成后运行 interviews-helper status --json，并用 interviews-helper search 做三次检索验证。
7. 汇报来源数、题目数、失败项和产物路径，不提交 data/ 或浏览器 Profile。
```

Agent 应负责：

- 根据岗位补充合理关键词和公开 URL；
- 读取 `status --json` 判断是否需要续跑；
- 对召回结果进行 OCR 纠错、复合题拆分、标签补充和答案生成；
- 回答时引用 `sources`，将生成答案与采集原题分开保存。

确定性代码负责浏览器生命周期、访问间隔、原始快照、断点和数据库。现阶段一个 Agent 足够；没有评测集之前，引入多个 Agent 只会增加调用成本和结果不稳定性。

## 9. 命令速查

### `collect`

```text
interviews-helper collect --job 岗位 [选项]
```

常用选项：

| 参数 | 默认值 | 作用 |
| --- | --- | --- |
| `--job` | 必填 | 目标岗位 |
| `--keywords` | 自动生成 | 逗号分隔的小红书搜索词 |
| `--url-file` | 无 | 公开文章 URL 文件 |
| `--limit` | `3` | 每个关键词最多处理的笔记数 |
| `--delay` | `15` | 页面操作间隔秒数，最低会限制为 3 秒 |
| `--manual-login-wait` | `300` | 登录或验证等待秒数 |
| `--no-ocr` | 关闭 | 禁用图片 OCR |
| `--ocr-max-images` | `9` | 单篇最多 OCR 图片数 |
| `--backend` | `cdp` | 浏览器连接方式：`cdp` 或 `persistent` |
| `--proxy` | 系统环境变量 | 显式浏览器代理地址 |
| `--run-id` | 自动 | 精确恢复某项运行 |
| `--no-resume` | 关闭 | 强制建立新运行 |

### 其他命令

```powershell
interviews-helper build [--seed FILE] [--database FILE] [--output FILE]
interviews-helper search "QUERY" [--grep REGEX] [--top-k N] [--json]
interviews-helper login {xhs,nowcoder,zhihu,weixin} [--wait SECONDS]
interviews-helper status [--json]
```

查看完整参数：

```powershell
interviews-helper --help
interviews-helper collect --help
interviews-helper search --help
```

## 10. 项目结构

```text
Interviews_Helper/
├─ src/interviews_helper/
│  ├─ cli.py                 命令行与 Agent 接口
│  ├─ browser.py             Chrome/CDP 生命周期
│  ├─ config.py              工作目录与浏览器路径
│  ├─ models.py              来源数据模型
│  ├─ service.py             建库服务编排
│  ├─ retrieval.py           grep、向量和 RRF
│  ├─ platforms/
│  │  ├─ xiaohongshu.py      搜索、详情、多图和 OCR
│  │  └─ public.py           牛客、知乎、公众号与普通网页
│  ├─ pipeline/questions.py  抽题、分类、规范化和去重
│  ├─ storage/
│  │  ├─ checkpoint.py       原子断点状态
│  │  └─ repository.py       JSON 快照与 SQLite
│  └─ report/
│     ├─ builder.py          HTML 报告构建
│     └─ template.html       报告模板
├─ examples/                 不含真实面经的最小输入示例
├─ tests/                    离线单元测试
├─ AGENTS.md                 Agent 操作边界
├─ pyproject.toml            现代 Python 构建入口
└─ setup.cfg                 版本、依赖和 CLI 发布配置
```

## 11. 数据库结构

SQLite 中包含四类核心信息：

- `posts`：独立来源及其正文、平台、完整性和 OCR 统计；
- `questions`：去重后的规范问题、主题、频次和质量分；
- `question_sources`：题目与来源的多对多关系及证据位置；
- `meta`：数据库 Schema 版本和生成时间。

稳定 ID 由规范来源标识或规范题面哈希生成。一个问题可以关联多个独立来源，频次按独立来源计算，而不是按重复文本行计算。

## 12. 常见问题排查

### 提示“没有找到 Chrome/Edge”

确认浏览器已经安装。程序会检查 Windows 常用安装路径、macOS Application 路径，以及 Linux 的 `google-chrome`、`chromium` 和 `msedge` 命令。自定义安装位置可以在 `src/interviews_helper/config.py` 的 `CHROME_PATHS` 中补充。

### Chrome 打开后立即退出或提示 Profile 被占用

不要同时打开两个使用同一 `.browser-profile-*` 的进程。关闭占用该 Profile 的 Chrome，再重新运行相同命令即可续跑。

### 页面一直显示登录或安全验证

由用户本人在打开的浏览器中完成操作。程序不会自动点击验证码。等待超时后查看 `status --json`，保留原参数稍后重试。

### 小红书搜索结果为零

先运行 `login xhs`，确认登录后能在同一浏览器窗口正常搜索。若出现验证，停止程序并隔一段时间再试；不要增加并发或缩短延迟。

### 牛客或知乎没有自动搜索

这是当前功能边界。请先收集具体公开 URL，写入 `public_urls.txt`，再通过 `--url-file` 采集。

### OCR 没有提取出问题

确认没有使用 `--no-ocr`，并检查 `data/images/<内容ID>/` 是否存在图片。OCR 结果会用 `[图片OCR 第N页]` 标记；低质量图片会保留低置信度，需要 Agent 或人工复核。

### pip 安装时出现 SSL、代理或 `bdist_wheel` 错误

先升级 pip：

```powershell
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

如果网络暂时不可用，但依赖已经安装，可执行 `python setup.py develop`。Windows 的 `run.ps1` 也包含这一兼容回退。

### 如何配置代理

`run.ps1` 会读取 Windows 系统代理，也可以显式传入：

```powershell
.\run.ps1 collect --job "后端开发" --proxy "http://127.0.0.1:7890"
```

CLI 还会读取当前进程的 `HTTPS_PROXY` 或 `HTTP_PROXY`。本机 CDP 连接固定使用 `127.0.0.1`，不会经过外部代理。

## 13. 隐私、平台规则与开源边界

本项目用于个人、低频、可追溯的资料整理：

- 只读取用户能够正常访问的页面；
- 不绕过登录、验证码、付费墙或访问控制；
- 不提供签名伪造、账号池、Cookie 导出或高频并发；
- 不主动采集评论、联系方式、学校等与题库无关的个人信息；
- OCR 在本机执行，不把图片上传到第三方识别服务；
- 发布自己的题库前，应再次检查来源平台规则和作者授权范围。

代码采用 MIT License，不代表采集到的文章、图片和 OCR 文本自动获得 MIT 授权。详细规则见 [DATA_POLICY.md](DATA_POLICY.md) 和 [SECURITY.md](SECURITY.md)。

提交代码前请确认以下内容没有出现在 `git status` 中：

```text
data/
.browser-profile-*/
seed_data.json
public_urls.txt
interviews.html
任何 Cookie、请求头、代理凭据或真实截图
```

## 14. 开发、测试与发布

安装开发依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

运行测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

构建发行包：

```powershell
.\.venv\Scripts\python.exe -m pip install build
.\.venv\Scripts\python.exe -m build
```

CI 会在 Windows 与 Linux 的 Python 3.10、3.12 上验证安装、测试和 CLI。新增平台时，请把站点差异放在 `platforms/`，增加不含真实个人内容的 fixture，并保持存储、断点和报告层不依赖具体平台。

贡献流程见 [CONTRIBUTING.md](CONTRIBUTING.md)，后续能力见 [ROADMAP.md](ROADMAP.md)，架构与 Agent 边界见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 15. 设计参考

本项目参考了以下开源项目的工程思路，并围绕个人面经库独立实现：

- [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)：真实浏览器登录态和平台分层；
- [Crawl4AI](https://github.com/unclecode/crawl4ai)：可恢复的长任务；
- [Firecrawl](https://github.com/firecrawl/firecrawl)：清晰的工具接口；
- [ScrapeGraphAI](https://github.com/ScrapeGraphAI/Scrapegraph-ai)：Agent 内容处理流水线。

如果你只想先确认项目是否适合自己，请从第 3 节的脱敏示例开始；它不会访问任何外部面经页面。
