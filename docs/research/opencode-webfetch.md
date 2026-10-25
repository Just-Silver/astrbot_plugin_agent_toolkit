<!-- 职责：记录 OpenCode webfetch 工具的行为契约、分层实现、HTML→Markdown 能力边界与已知缺陷；不写 AstrBot 侧的取舍和实现决策。 -->

# OpenCode `webfetch` 工具分析

资料采集自 `E:\Code\Projects\Agent\Externals\opencode`（采集日期 2026-10-26）。

相关文件：

| 文件 | 行数 | 内容 |
|---|---|---|
| `packages/core/src/tool/plugin/webfetch.ts` | 181 | 工具定义、HTTP 抓取、格式选择、纯文本抽取 |
| `packages/core/src/tool/html-markdown.ts` | 658 | HTML→Markdown 状态机 |
| `packages/core/src/tool/http-body.ts` | 30 | 有界流式读取 |
| `packages/core/src/mime.ts` | — | MIME 文本判定 |
| `packages/core/test/tool-webfetch.test.ts` | — | 43 个行为契约用例 |

## 工具契约

```
名称: webfetch
输入:
  url      string   必填，仅允许 http:// 或 https://
  format   enum      text | markdown | html，默认 markdown
  timeout  number    秒，>0 且 <=120，默认 30
输出:
  { url, contentType, format, output }
```

按 `format` 发送不同 `Accept`：

| format | Accept |
|---|---|
| `markdown` | `text/markdown;q=1.0, text/x-markdown;q=0.9, text/plain;q=0.8, text/html;q=0.7, */*;q=0.1` |
| `text` | `text/plain;q=1.0, text/markdown;q=0.9, text/html;q=0.8, */*;q=0.1` |
| `html` | `text/html;q=1.0, application/xhtml+xml;q=0.9, text/plain;q=0.8, text/markdown;q=0.7, */*;q=0.1` |

固定请求头：`User-Agent`（伪装 Chrome）、`Accept`、`Accept-Language: en-US,en;q=0.9`。

## 处理流程

```
校验 URL 协议（仅 http/https）
  → 权限校验（OpenCode Permission.Service，AstrBot 无对应层）
  → GET，403 且响应头 cf-mitigated: challenge 时换 UA 重试一次
  → 取 content-type，解析 MIME
  → 图片（除 svg）直接失败；非文本 MIME 直接失败
  → 有界读取响应体（上限 5MB）
  → TextDecoder 解码
  → 按 content-type 与 format 转换
  → 返回 { url, contentType, format, output }
```

## 有界读取（`http-body.ts`）

1. 若 `content-length` 可解析且超过上限 → 立即失败，不读响应体。
2. 按 `min(上限, declared || 64KB)` 预分配缓冲。
3. 流式累加，任一块导致总量超限 → 失败。
4. 缓冲不足时翻倍扩容，上限封顶 5MB。

上限常量：`MAX_RESPONSE_BYTES = 5 * 1024 * 1024`。

## MIME 白名单（`mime.ts:19`）

`isTextual(mime)` 放行：

- 空字符串
- `text/*`
- `application/json`、`*+json`
- `application/xml`、`*+xml`
- `application/javascript`、`application/x-javascript`

其余一律拒绝。图片判定更严：`image/*` 中除 `image/svg+xml`、`image/vnd.fastbidsheet` 外都视为不可处理。

## HTML→Markdown 能力边界

基于 `htmlparser2` 的事件式解析（`onopentag` / `ontext` / `onclosetag`），维护一个 Frame 栈与多个全局状态（当前代码块、链接、列表、表格、引用深度、缩进）。

支持：

| 类别 | 细节 |
|---|---|
| 标题 | `h1`~`h6` → `#`~`######` |
| 块级 | `address` `article` `aside` `details` `dialog` `div` `dl` `fieldset` `figcaption` `figure` `footer` `form` `header` `main` `nav` `p` `section` `summary` |
| 换行/分隔 | `br` → 行尾两空格换行；`hr` → `---` |
| 行内强调 | `strong`/`b`、`em`/`i` 等（`inlineMarker`） |
| 列表 | `ul`/`ol`/`li`，支持 `ol[start]`、`li[value]`、嵌套缩进按父标记实际宽度、续行缩进 |
| 引用 | `blockquote` 嵌套，前缀深度上限 8 层 |
| 代码 | `pre`/`code`，捕获 `class` 里的 `language-*` / `lang-*`，围栏按内容中最长反引号加长，保证可闭合 |
| 表格 | GFM 表格 + `caption`；有 `colspan`/`rowspan` 时降级为行文本；嵌套表扁平化；单元格内 `|` 转义 |
| 链接 | `a`，可被块级元素打断后恢复（`suspendedLink`），嵌套 `a` 自动收尾 |
| 图片 | `img` → `![alt](src "title")` |
| 定义列表 | `dt` → 粗体，`dd` → `: ` 前缀 |
| 折叠块 | `details`/`summary`，未展开的 `details` 内容视为不可见 |
| 可见性抑制 | `hidden` 属性、`aria-hidden="true"`、`<head>` 整棵子树 |
| 省略标签 | `script` `style` `noscript` `iframe` `object` `embed` `meta` `link` `template` |

预算与兜底：

- 总输出上限 5MB，正文内容上限 5MB - 64KB（给收尾语法留空间）。
- 按 UTF-8 字节切片，二分查找不截断多字节字符。
- 标签嵌套深度超过 10000 时进入 fallback：停止结构化输出，只保留可见文本。
- 超长代码围栏会按可用预算裁剪，并保证围栏闭合。

## 已知缺陷

1. **没有 SSRF 防护**。`assertHttpUrl` 只校验 `url.protocol` 是 `http:`/`https:`，不解析 IP、不拦内网/回环/link-local/云元数据地址。
2. **不做正文提取**。整页转 Markdown，导航、侧栏、页脚、评论全部保留。对聊天机器人场景会导致单次工具结果塞满上下文。
3. **依赖 OpenCode 运行时**：`effect`、`HttpClient`、`Permission.Service`、managed storage 预览，AstrBot 都没有对应实现。
4. **不处理 charset**。直接用 `TextDecoder` 按 UTF-8 解码，GBK 等页面会乱码。
5. **不缓存**。同一 URL 重复抓取无复用。

## TS → Python 迁移映射

| OpenCode | Python 对应 | 迁移判断 |
|---|---|---|
| `assertHttpUrl` | `urllib.parse.urlparse` + 协议校验 | 逻辑照搬，需**补充** IP 解析与私网拒绝 |
| `Effect HttpClient` + `HttpClientResponse` | `httpx` / `aiohttp` 流式请求 | 重写；AstrBot 约定 `trust_env=True` 跟随系统代理 |
| `collectBoundedResponseBody` | 流式累加 + `content-length` 预检 | 逻辑照搬 |
| `Mime.isTextual` | 同名白名单函数 | 逻辑照搬 |
| `TextDecoder` 解码 | `response.charset_encoding` / `charset_normalizer` | 需**增强** |
| `convertHTMLToMarkdown`（658 行） | `trafilatura` 正文提取 + `markdownify` 转换 | **不逐行翻译**，见下 |
| `extractTextFromHTML` | `html.parser` 或 trafilatura 的纯文本输出 | 可简化 |
| `Permission.Service` | AstrBot `_PermissionGuardedTool` + 插件配置 | 不复用，改用平台机制 |
| managed storage 预览 | 自行截断 + 提示续读 | 需**新增** |
| `MAX_RESPONSE_BYTES` / `CONTENT_BYTES` | 同值常量 | 可直接沿用 |

### 为什么不逐行翻译 658 行转换器

- 它解决的是"整页→Markdown"，而聊天机器人需要的是"正文→Markdown"，目标不同。
- `trafilatura` 是专做正文提取的成熟实现，输出质量与维护成本都优于手写状态机。
- 手写状态机的价值在于**零依赖**；一旦引入 `trafilatura`，逐行翻译就没有收益。

可复用的是它的**工程契约**而非实现：字节预算、深度兜底、围栏闭合、表格降级、可见性抑制、MIME 白名单、有界读取。这些应作为新实现的行为要求与测试用例来源。

## 测试用例清单（可改写为 pytest）

`packages/core/test/tool-webfetch.test.ts` 的 43 个用例覆盖：

- 输入校验：默认 format、timeout 为 0 或超上限时拒绝
- HTML→文本：省略 script/style 等后保留可见文本
- 标题、行内语义、链接、图片、换行、分隔线
- 行内代码与 `pre` 原文保留、围栏安全闭合
- 嵌套有序/无序列表结构与编号
- 表格、`caption`、`span` 降级、嵌套表扁平化
- 实体解码、空白归一化、不粘连单词
- `hidden`/`aria-hidden`/`<head>` 抑制
- 畸形输入下的确定性与边界（不抛异常、输出不超过输入）
- 5MB 预算与收尾空间
- 深度兜底、长围栏、Unicode、链接跨块恢复

## 参考来源

- 仓库：OpenCode（`E:\Code\Projects\Agent\Externals\opencode`）
- 工具名与行为以该仓库 current on-disk 代码为准
