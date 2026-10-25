<!-- 职责：定义 web_fetch 工具的设计、契约、实现约束与验收标准；不写发布流程与仓库运营。 -->

# web_fetch 设计规格

日期：2026-10-26
状态：已批准，待实现

## 目标

给 AstrBot Agent 一个**不依赖任何搜索服务商 API Key** 的网页读取工具：用户丢来一个链接，Agent 能读到正文，而不是只有一串 URL。

## 范围

**做**

- 注册一个 LLM 工具 `web_fetch`
- HTTP(S) 抓取、正文提取、Markdown/纯文本输出
- 大小、超时、编码、重定向、SSRF 的完整处理
- 长文截断与按 `start` 续读

**不做**

- 不监听消息事件，不做 URL 自动识别与自动注入
- 不做搜索（`web_search` 已有内置实现）
- 不做域名黑白名单
- 不做结果缓存
- 不解析 PDF、Office 文档（后续版本）
- 不注册任何其他工具

## 工具契约

```python
name = "web_fetch"

parameters = {
    "type": "object",
    "properties": {
        "url":    {"type": "string",  "description": "The http:// or https:// URL to read."},
        "format": {"type": "string",  "enum": ["markdown", "text"],
                   "description": "Output format. Defaults to markdown."},
        "start":  {"type": "integer", "description": "Character offset to start reading from. Defaults to 0."},
    },
    "required": ["url"],
}
```

`description`（给模型看）：

> Read the main content of a web page and return it as Markdown or plain text. Use it when the user shares a link or asks about a specific page. Only http and https are supported. Long pages are truncated; call again with `start` to continue.

返回：`ToolExecResult`，即字符串。

## 处理流程

```
1. 校验 URL：scheme ∈ {http, https}，host 非空，长度 <= 2048
2. SSRF 校验：解析 host 全部 A/AAAA 记录，任一地址非全局即拒绝
3. GET 请求（不自动跟随重定向）
4. 手动跟随重定向，最多 5 跳，每跳重复步骤 1-2
5. 403 且响应头 cf-mitigated == challenge → 换 UA 重试一次
6. 大小检查：content-length 预检，再流式累加，上限 5MB
7. MIME 白名单检查
8. 按 content-type 解码：HTTP charset → utf-8 → gb18030 → 替换非法字节（`errors="replace"`）
9. HTML 走正文提取，非 HTML 原样返回
10. 截断并按 start 切片
11. 拼接来源头与续读提示
```

## 安全：SSRF 防护

**无开关，始终启用。** 对 Docker 部署尤其必要：容器内 `127.0.0.1`、`172.16.0.0/12` 指向 AstrBot 自身或其他服务。

判定方式：`ipaddress.ip_address(addr).is_global` 为 `False` 即拒绝。覆盖回环、私网、link-local、CGNAT、保留段、组播、未指定地址与 IPv6 ULA。

规则：

- host 是 IP 字面量时直接判定，不做 DNS
- host 是域名时必须解析，解析失败即拒绝
- **任一**解析结果非全局即拒绝（防 DNS 重绑定的一半）
- 重定向目标重复完整校验，禁止跳到非 http(s)

DNS 解析用 `asyncio.to_thread(socket.getaddrinfo, ...)`，避免阻塞事件循环。

## 抓取细节

| 项 | 值 |
|---|---|
| 客户端 | `httpx.AsyncClient(trust_env=True, follow_redirects=False)` |
| 超时 | connect 10s / read `timeout` / write 10s / pool 10s |
| User-Agent | Chrome 桌面 UA |
| Accept | markdown: `text/markdown;q=1.0, text/html;q=0.9, text/plain;q=0.8, */*;q=0.1`<br>text: `text/plain;q=1.0, text/html;q=0.9, */*;q=0.1` |
| Accept-Language | `zh-CN,zh;q=0.9,en;q=0.8` |
| 响应上限 | 5 MB |
| 重定向上限 | 5 跳 |

MIME 白名单（与 OpenCode 一致）：

- 空 content-type
- `text/*`
- `application/json`、`*+json`
- `application/xml`、`*+xml`
- `application/javascript`、`application/x-javascript`

图片（含 `image/svg+xml`）与其他类型一律拒绝，错误信息带上实际 content-type。

## 正文提取

HTML 走两条路径：

1. `trafilatura.extract(html, output_format="markdown"|"txt", include_links=True, include_tables=True, favor_recall=True)`
2. 返回空时回退 `markdownify(html, heading_style="ATX", strip=["script", "style", "noscript", "iframe", "object", "embed", "template"])`

**依赖降级链**：`trafilatura` 导入失败 → `markdownify`；两者都不可用或抛错 → 标准库 `html.parser` 去标签。任何一环失败都不能让工具抛异常，最差也要返回整页纯文本。

回退的意义：SPA 或纯列表页 trafilatura 可能判空，此时宁可给整页文本，也不能返回"读不到"。

非 HTML（text/plain、JSON、XML）不做任何转换，原样返回。

标题提取：从 `<title>` 取，失败则留空。

## 截断与续读

- 默认单次返回 8000 字符（配置项 `max_chars`）
- `start` 超出正文长度时返回 `(no content)`，并提示 `[start=<n> is beyond the end; total length is <total> characters.]`
- 截断时在正文后追加：

```
[Content truncated: showed 8000 of 23456 characters. Call web_fetch with start=8000 to continue.]
```

## 输出格式

```
# <title>            ← 有标题时

<content>

---
URL: <最终 URL>
[Content truncated: ...]   ← 仅在截断时
```

无标题时省略标题行。

## 错误返回

统一单行 `Error: <reason>`，与 AstrBot 内置工具的错误风格一致。分支：

| 场景 | 文本 |
|---|---|
| 缺少 url | `Error: url is required.` |
| 协议不支持 | `Error: only http and https URLs are supported.` |
| 缺少 host | `Error: URL has no host.` |
| URL 过长（>2048） | `Error: URL is too long.` |
| 私网地址 | `Error: refusing to fetch a private or reserved address.` |
| DNS 失败 | `Error: cannot resolve host.` |
| 连接失败 | `Error: request failed: <exc>` |
| 超时 | `Error: request timed out after <n>s.` |
| 重定向过多（>5） | `Error: too many redirects.` |
| HTTP 4xx/5xx | `Error: HTTP <status>.` |
| 响应过大 | `Error: response exceeds 5 MB limit.` |
| 类型不支持 | `Error: unsupported content type: <mime>.` |

不抛异常给 Agent Runner，全部转成错误字符串。

## 配置

`_conf_schema.json` 三项，全部有默认值，不配置即可正常工作：

| key | type | 默认 | 说明 |
|---|---|---|---|
| `enabled` | bool | true | 是否注册工具 |
| `max_chars` | int | 8000 | 单次返回字符上限，slider 1000–50000 |
| `timeout` | int | 30 | 单次请求超时秒数，slider 5–120 |

`enabled=false` 时不调用 `add_llm_tools`，插件静默不注册工具。

## 依赖

`requirements.txt`：

```
trafilatura>=2.0.0
markdownify>=0.13.0
httpx>=0.27.0
```

风险：`trafilatura` 依赖 `lxml`。官方镜像 `python:3.12-slim` 没有 `libxml2-dev`，必须命中 manylinux wheel。实现完成后需在干净环境验证一次安装。

即使依赖安装失败，插件也必须能加载并注册工具：正文提取走降级链，最差返回整页纯文本。

## 项目结构

```
astrbot_plugin_agent_toolkit/
  main.py                      # Main(Star)：读配置、注册工具、terminate
  webfetch/
    __init__.py
    tool.py                    # WebFetchTool(FunctionTool)
    fetch.py                   # URL 校验、SSRF、HTTP 抓取、重定向
    extract.py                 # 正文提取、Markdown 转换、截断
    errors.py                  # FetchError
  tests/
    test_ssrf.py
    test_fetch.py
    test_extract.py
  _conf_schema.json
  ruff.toml
  requirements.txt
  pytest.ini
  metadata.yaml
  README.md
```

插件内部一律使用相对导入（`from .webfetch.tool import WebFetchTool`），避免与其它插件的顶层模块冲突。

## 代码规范

- `ruff` 最新版，配置对齐 AstrBot 主项目门禁（`F/W/E/ASYNC/C4/Q/I/UP`，忽略 `F403/F405/E501/ASYNC230/ASYNC240`），`line-length = 120`，`target-version = "py310"`
- docstring 用 Google 格式
- 注释只解释"为什么"，不写改动说明

## 测试

只测业务行为，外部边界（HTTP、DNS）用假件。

| 用例 | 断言 |
|---|---|
| 私网/回环/link-local/CGNAT 地址 | 拒绝，返回私网错误 |
| 域名解析到私网地址 | 拒绝 |
| 重定向到私网地址 | 拒绝 |
| 非 http(s) 协议 | 拒绝 |
| 图片 content-type | 拒绝 |
| 无 content-type 的纯文本 | 允许，原样返回 |
| 超过 5MB | 拒绝 |
| 正常 HTML | 返回正文，导航文本不出现 |
| trafilatura 提取为空 | 回退后仍有内容 |
| 长正文 | 截断并带续读提示 |
| `start` 续读 | 返回后续片段，不重复 |
| `start` 超过总长 | 空内容 + 总长度提示 |
| 4xx/5xx | 返回 `Error: HTTP <status>` |
| 超时 | 返回超时错误，不抛异常 |

## 验收标准

1. `ruff format --check .` 与 `ruff check .` 通过
2. `pytest` 全部通过
3. 未配置任何东西时，插件加载后 WebUI 工具页出现 `web_fetch`
4. 给一个真实公网 URL，能返回正文 Markdown
5. 请求 `http://127.0.0.1:6185` 被拒绝
6. 在 `python:3.12-slim` 下 `pip install -r requirements.txt` 一次成功
