<!-- 职责：定义插件 WebUI（工具台视图）的界面结构、接口契约与验收标准；不写发布流程与实现步骤。 -->

# 工具台 WebUI 设计规格

日期：2026-10-26
状态：设计已确认，待实现

## 目标

给 `astrbot_plugin_agent_toolkit` 提供一个人工可用的管理界面：看到插件当前暴露了哪些工具，并且能直接测试，不必发消息、不必跑命令。

## 范围

**做**

- 一个视图 `toolkit`，两栏布局：左栏工具列表，右栏选中工具的详情与测试台
- 工具列表从运行中的工具管理器读取，有几个工具就显示几个
- `web_fetch` 的测试台：输入 URL，显示与模型完全一致的输出
- 跟随 AstrBot 亮/暗主题与语言

**不做**

- 不写回插件配置（已有原生配置页）
- 不做抓取历史、不做统计
- 不渲染 Markdown（结果展示源码）
- 不做工具启停开关（AstrBot 工具页负责）
- 不引入前端构建链

## 目录结构

```
views/
  toolkit/
    index.html
    style.css
    app.js
.astrbot-plugin/
  i18n/
    zh-CN.json
    en-US.json
webfetch/
  webapi.py          # 新增：Web API handler 与可测的纯函数
tests/
  test_webapi.py     # 新增
```

## 后端接口

路由必须带插件名前缀；视图端只写相对路径。

| 方法 | 后端路由 | 视图 endpoint | 用途 |
|---|---|---|---|
| GET | `/astrbot_plugin_agent_toolkit/tools` | `tools` | 工具列表 |
| POST | `/astrbot_plugin_agent_toolkit/tools/web_fetch/test` | `tools/web_fetch/test` | 执行一次抓取 |

### GET `tools`

返回：

```json
{
  "tools": [
    {
      "name": "web_fetch",
      "active": true,
      "description": "Read the main content of a web page ...",
      "parameters": { "type": "object", "properties": {}, "required": ["url"] }
    }
  ]
}
```

数据来源：`context.get_llm_tool_manager().func_list`，只保留 `handler_module_path` 以本插件包名为前缀的项（`handler_module_path or ""`，前缀取 `Main.__module__.rsplit(".", 1)[0]`）。字段映射：

- `name` ← `tool.name`
- `active` ← `tool.active`
- `description` ← `tool.description`
- `parameters` ← `tool.parameters`

列表按 `name` 排序，保证每次打开顺序稳定。

### POST `tools/web_fetch/test`

请求：

```json
{ "url": "https://example.com", "max_chars": 8000, "timeout": 30 }
```

`url` 必填非空；`max_chars` 缺省 8000，clamp 到 1000–50000；`timeout` 缺省 30，clamp 到 5–120。非数字或非法值回落到默认值，不报错。

返回：

```json
{
  "ok": true,
  "output": "# Example Domain\n\n...\n\n---\nURL: https://example.com/",
  "elapsed_ms": 420,
  "chars": 156,
  "truncated": false,
  "final_url": "https://example.com/"
}
```

- `ok`：`output` 是否不以 `Error:` 开头
- `output`：`run_fetch` 的原始返回值，一个字符都不改
- `elapsed_ms`：整次调用耗时，四舍五入到毫秒
- `chars`：`len(output)`
- `truncated`：`output` 是否包含 `Content truncated`
- `final_url`：从 `output` 里的 `URL: ` 行解析；解析不到时为空字符串

`url` 为空时返回 `error_response("url is required", status_code=400)`，前端按请求失败处理。

## 可测性拆分

`webfetch/webapi.py` 里把纯逻辑与平台 IO 分开：

- `def clamp_int(value: object, low: int, high: int, default: int) -> int`
- `def normalize_test_request(payload: dict) -> tuple[str, int, int] | None`：返回 `(url, max_chars, timeout)`，`url` 为空时返回 `None`
- `def build_test_result(output: str, elapsed_ms: float) -> dict`：组装上面的返回体
- `def collect_tools(func_list, package_prefix: str) -> list[dict]`：过滤并映射工具列表

handler 只负责读请求、调用上述函数、返回响应。单元测试覆盖这四个函数，不需要启动 AstrBot。

## 页面结构

```
┌─────────────────────────────────────────────┐
│ Agent Toolkit            1 个工具 · 1 个已启用 │
├───────────┬─────────────────────────────────┤
│ 工具       │ web_fetch        已启用          │
│ ● web_fetch│ 抓取网页正文，返回 Markdown…      │
│           │ [ URL ........................ ] [抓取] │
│           │ 字符上限 [8000]  超时 [30] 秒  仅本次生效 │
│           │ 0.42s · 156 字符 · 未截断 · 最终 URL    │
│           │ ┌─────────────────────────────┐ │
│           │ │ # Example Domain            │ │
│           │ │ …                           │ │
│           │ └─────────────────────────────┘ │
├───────────┴─────────────────────────────────┤
│ 结果与模型看到的完全一致        Enter 抓取 · Ctrl+C 复制 │
└─────────────────────────────────────────────┘
```

- 左栏宽 168px，只渲染真实存在的工具；没有工具时右栏显示「当前没有注册任何工具」
- 首次打开默认选中列表第一项
- 切换工具只改变右栏内容，不重新请求列表
- 窄屏（<720px）：左栏变成顶部横向滚动的一行标签

## 测试台交互

- 点击「抓取」或按 Enter 触发；请求期间按钮进入 loading 且禁止再次提交
- 成功后更新元信息行与结果区
- `ok=false` 时结果区用错误色（红）显示 `output` 原文
- 请求本身失败（HTTP 错误）时在结果区上方显示一行错误提示，保留上一次结果
- 「复制」按钮复制 `output` 全文，成功后按钮文案短暂变为「已复制」
- 字符上限 / 超时输入只影响本次请求，不写配置

## 视觉规范

- 全部颜色走 CSS 变量，前缀 `--tk-`；`[data-theme="dark"]` 下覆盖一套
- 亮色：背景 `#fbfbfc`、面板 `#ffffff`、边框 `#e4e6ea`、正文 `#1c1f23`、次要 `#6b7280`、主色 `#4f7df3`
- 暗色：背景 `#15171b`、面板 `#1b1e24`、边框 `#2b2f37`、正文 `#e6e8eb`、次要 `#8b93a1`、主色 `#6f9bff`
- 圆角：外层 14px、控件 8px；结果区等宽字体、行高 1.65
- 主色只用于按钮、标题前缀、选中项背景，其余用中性色
- 不使用图片、图标字体或外部 CDN

## 国际化

`.astrbot-plugin/i18n/zh-CN.json` 与 `en-US.json`，`views.toolkit` 下提供：

| key | 中文 | 用途 |
|---|---|---|
| `title` | 工具台 | 视图名称 |
| `description` | 查看插件提供的工具并直接测试 | 视图描述 |
| `heading` | Agent Toolkit | 页面标题 |
| `tools` | 工具 | 左栏标题 |
| `enabled` / `disabled` | 已启用 / 已禁用 | 状态徽标 |
| `fetch` | 抓取 | 按钮 |
| `max_chars` / `timeout` / `seconds` | 字符上限 / 超时 / 秒 | 参数标签 |
| `elapsed` / `chars` / `truncated` / `not_truncated` | 耗时 / 字符 / 已截断 / 未截断 | 元信息 |
| `copy` / `copied` | 复制 / 已复制 | 复制按钮 |
| `empty` | 当前没有注册任何工具 | 空状态 |
| `only_once` | 仅本次测试生效 | 参数提示 |
| `request_failed` | 请求失败 | HTTP 错误提示 |

页面文案通过 `bridge.t("views.toolkit.<key>", fallback)` 读取，并通过 `bridge.onContext()` 响应语言切换。

## 错误处理

| 场景 | 表现 |
|---|---|
| URL 为空 | 前端禁用按钮，不发请求 |
| 参数非法 | 后端回落到默认值，正常执行 |
| 抓取失败（工具返回 `Error:`） | 红字显示原文，HTTP 200 |
| 接口异常 | 前端显示「请求失败」，保留上次结果 |
| 工具列表为空 | 右栏空状态文案 |

## 安全

- 测试台只调用固定的 `web_fetch`，不接受前端传入任意工具名
- URL 校验、SSRF 拦截沿用 `run_fetch`，页面不绕过
- 参数 clamp 在后端执行，不信任前端数值
- 视图运行在受限 iframe，所有请求经 bridge，不直接访问 Dashboard 凭据

## 测试

后端单元测试（`tests/test_webapi.py`，不启动 AstrBot）：

| 用例 | 断言 |
|---|---|
| `clamp_int` 低于下限 | 返回下限 |
| `clamp_int` 高于上限 | 返回上限 |
| `clamp_int` 非数字 | 返回默认值 |
| `normalize_test_request` 空 url | 返回 `None` |
| `normalize_test_request` 缺省字段 | 用默认 8000 / 30 |
| `normalize_test_request` 越界字段 | 被 clamp |
| `build_test_result` 正常输出 | `ok=True`、`chars` 正确、`final_url` 解析正确 |
| `build_test_result` 错误输出 | `ok=False` |
| `build_test_result` 截断输出 | `truncated=True`、`final_url` 仍能解析 |
| `collect_tools` 只保留本插件工具 | 混入其他前缀的工具被过滤 |
| `collect_tools` 排序稳定 | 按 name 升序 |

前端手工验收（iframe 内无法自动化）：

| 步骤 | 期望 |
|---|---|
| 插件详情页打开「工具台」 | 页面加载，左栏出现 `web_fetch` |
| 输入 `https://example.com` 点抓取 | 结果与命令行 `run_fetch` 输出一致 |
| 输入 `http://127.0.0.1:6185/` | 红字 `Error: refusing to fetch...` |
| 字符上限改 50 再抓取 | 结果被截断，提示 50/N |
| 点击复制 | 剪贴板内容与结果区一致，按钮短暂显示「已复制」 |
| 切换亮/暗主题 | 颜色跟随，无写死色块 |
| 窗口缩到 720px 以下 | 左栏折成顶部标签行 |
| 切换到 English | 文案变英文 |

## 验收标准

1. `pytest` 全绿，`ruff check .` 通过
2. 插件详情页能打开「工具台」视图
3. 工具列表只显示本插件的工具，数量与 `func_list` 一致
4. 测试台输出与命令行 `run_fetch` 完全一致
5. 亮/暗主题、中/英文切换正常
6. 窄屏不出现横向溢出

## 已知限制

- 页面为只读 + 测试，不承担配置修改
- 每次测试都会真实抓取，没有缓存
- 测试结果不持久化，刷新即丢
