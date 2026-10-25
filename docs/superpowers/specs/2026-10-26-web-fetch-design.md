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
9. HTML 走 trafilatura，提取为空即报错；非 HTML 原样返回
10. 截断并按 start 切片
11. 拼接来源头与续读提示
```

## 安全：SSRF 防护

**无开关，始终启用。** 对 Docker 部署尤其必要：容器内 `127.0.0.1`、`172.16.0.0/12` 指向 AstrBot 自身或其他服务。

判定方式：**显式 CIDR 清单 + `is_global` 兜底**。命中清单直接拒绝；未命中再判 `is_global`，为 `False` 也拒绝。

不能只用 `is_global`：实测 `224.0.0.1`、`ff02::1`、`64:ff9b::1` 的 `is_global` 都是 `True`（组播和 NAT64 会被放行）。

写死清单：

| IPv4 | IPv6 |
|---|---|
| `0.0.0.0/8` | `::/128` |
| `10.0.0.0/8` | `::1/128` |
| `100.64.0.0/10` | `::ffff:0:0/96` |
| `127.0.0.0/8` | `64:ff9b::/96` |
| `169.254.0.0/16` | `100::/64` |
| `172.16.0.0/12` | `2001:db8::/32` |
| `192.0.0.0/24` | `2002::/16` |
| `192.0.2.0/24` | `fc00::/7` |
| `192.88.99.0/24` | `fe80::/10` |
| `192.168.0.0/16` | `ff00::/8` |
| `198.18.0.0/15` | |
| `198.51.100.0/24` | |
| `203.0.113.0/24` | |
| `224.0.0.0/4` | |
| `240.0.0.0/4` | |
| `255.255.255.255/32` | |

IPv4-mapped IPv6（`::ffff:0:0/96`）必须拆出内嵌 IPv4 再判，否则 `http://[::ffff:127.0.0.1]/` 能绕过。

规则：

- host 是 IP 字面量时直接判定，不做 DNS
- host 是域名时必须解析，解析失败即拒绝
- **任一**解析结果非全局即拒绝（防 DNS 重绑定的一半）
- 重定向目标重复完整校验，禁止跳到非 http(s)
- `blocked_hosts` 非空时先做域名匹配，命中即拒绝

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

只有一条路径：`trafilatura.extract(html, output_format="markdown"|"txt", include_links=True, include_tables=True, favor_precision=True)`。

`favor_precision=True` 是必须的：实测默认参数和 `favor_recall=True` 都会把 `<nav>` 的文本带进正文，只有 `favor_precision=True` 会剔除导航/页脚并输出正确的 `#` 标题。

判空只在 HTML 没有任何可提取文本节点时发生（实测）：

| 输入 | 结果 |
|---|---|
| 空 `<body>`、SPA 空容器、纯 `<img>` 页面 | `None` |
| 单句 `<p>hello</p>` | `"hello"` |
| 纯链接列表 | 链接文字 |
| 短文 + 导航 | 正文（含导航，除非 `favor_precision`） |

返回 `None` 或空字符串 → 工具返回 `Error: no readable content found in this page.`。不降级到全页转换。

`trafilatura` 在模块顶层导入。依赖缺失时让插件加载失败，由 AstrBot 输出加载错误日志；插件本身不做运行时检查，也不降级到其他实现。

非 HTML（text/plain、JSON、XML）不做任何转换，原样返回。

标题提取：从 `<title>` 取，失败则留空。

## 截断与续读

- 默认单次返回 8000 字符（配置项 `max_chars`）
- 截断必要性：AstrBot 的大结果溢出机制（落盘 + 预览，上限 27500 估算 token）只有在 `computer_use_runtime` 开启、`astrbot_file_read_tool` 存在时才生效。默认部署下不生效，大结果会原样进入上下文
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
| 正文提取为空 | `Error: no readable content found in this page.` |

不抛异常给 Agent Runner，全部转成错误字符串。

## 配置

`_conf_schema.json` 三项，全部有默认值，不配置即可正常工作：

| key | type | 默认 | 说明 |
|---|---|---|---|
| `enabled` | bool | true | 是否注册工具 |
| `max_chars` | int | 8000 | 单次返回字符上限，slider 1000–50000 |
| `timeout` | int | 30 | 单次请求超时秒数，slider 5–120 |
| `blocked_hosts` | list | `[]` | 额外要拦的域名。host 完全相等，或以 `.` + 该值结尾时拒绝 |

`enabled=false` 时不调用 `add_llm_tools`，插件静默不注册工具。

## 依赖

`requirements.txt`：

```txt
trafilatura>=2.0.0
httpx>=0.27.0
```

风险：`trafilatura` 依赖 `lxml`。官方镜像 `python:3.12-slim` 没有 `libxml2-dev`，必须命中 manylinux wheel。实现完成后需在干净环境验证一次安装。

依赖缺失时插件加载失败，AstrBot 的插件页会显示加载失败并打印错误日志。不做运行时检查，不静默降级。

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
| 组播地址（`224.0.0.1`、`ff02::1`） | 拒绝 |
| IPv4-mapped IPv6（`::ffff:127.0.0.1`） | 拒绝 |
| `blocked_hosts` 命中的域名及其子域 | 拒绝 |
| 域名解析到私网地址 | 拒绝 |
| 重定向到私网地址 | 拒绝 |
| 非 http(s) 协议 | 拒绝 |
| 图片 content-type | 拒绝 |
| 无 content-type 的纯文本 | 允许，原样返回 |
| 超过 5MB | 拒绝 |
| 正常 HTML | 返回正文，导航文本不出现 |
| 正文提取为空 | 返回 `Error: no readable content found in this page.` |
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
7. 人为让 `trafilatura` 导入失败时，插件加载失败并在日志中给出明确原因
