# astrbot_plugin_agent_toolkit

为 AstrBot Agent 提供一组通用工具的插件集合。当前提供 `web_fetch`：让 Agent 能读取网页正文，而不需要任何搜索服务商的 API Key。

## 提供的能力

| 工具 | 说明 |
|---|---|
| `web_fetch` | 抓取一个 http/https 链接，提取正文，返回 Markdown 或纯文本 |

模型在用户贴出链接或问某个页面时自行决定调用；插件不监听消息、不做自动抓取，不调用时不占用任何上下文。

## WebUI 工具台

插件在 WebUI 的插件详情页提供一个「工具台」视图：

- 左栏列出本插件注册的所有工具及启用状态，有几个显示几个
- 右栏输入 URL 直接执行一次 `web_fetch`，结果与模型看到的完全一致
- 可以临时调整字符上限与超时，仅本次生效，不写回配置

工具台不修改配置、不保存历史。配置仍在插件配置页。

## 开发

前端源码在 `webui/`（Vue 3 + Vite + Naive UI），构建产物在 `views/toolkit/`。修改前端后必须重新构建并提交产物：

```bash
cd webui
npm install
npm run build
```

安装插件的用户不需要 Node。

## 安装

在 AstrBot WebUI 的插件页通过仓库链接安装：

```
https://github.com/Just-Silver/astrbot_plugin_agent_toolkit
```

依赖（`trafilatura`、`httpx`）会随插件自动安装。装不上时插件加载失败，AstrBot 插件页会显示失败并打印原因。

## 配置

全部有默认值，不配置即可使用。

| 配置项 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `enabled` | bool | `true` | 是否注册 `web_fetch` 工具 |
| `max_chars` | int | `8000` | 单次返回的字符上限，超出后提示模型用 `start` 续读 |
| `timeout` | int | `30` | 单次请求超时（秒） |
| `blocked_hosts` | list | `[]` | 额外禁止访问的域名；子域同样生效，端口忽略 |

## 行为

- 只接受 `http://` 与 `https://`
- 单页上限 5 MB，最多跟随 5 次重定向，每次重定向都重新校验目标地址
- 拒绝私网、回环、link-local、CGNAT、组播、保留地址与 IPv4-mapped IPv6，**无开关**
- 按响应头 charset 解码，依次回退 `utf-8`、`gb18030`
- 正文提取使用 `trafilatura`，提取不到正文时返回明确错误，不返回整页 HTML
- Cloudflare 403 challenge 会换 UA 重试一次
- 失败一律返回 `Error: ...` 文本，不抛异常

## 已知限制

- 不解析 PDF、Office 文档与图片
- 纯前端渲染（SPA）且无服务端正文的页面会返回 `no readable content`
- 不做结果缓存
- 不提供搜索能力；需要搜索请使用 AstrBot 内置的联网搜索

## 来源声明

`web_fetch` 的工程约束（响应大小上限、MIME 白名单、重定向与 Cloudflare 处理、可见性抑制、字节预算）参考了 [OpenCode](https://github.com/sst/opencode) 的 `webfetch` 工具（`packages/core/src/tool/plugin/webfetch.ts`），按其 MIT 协议使用设计思路，未复制其 HTML→Markdown 实现。正文提取改用 [trafilatura](https://github.com/adbar/trafilatura)。

## 许可

MIT
