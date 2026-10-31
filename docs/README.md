# 文档地图

本仓库的文档只登记顶层入口，一行一篇。新增文档必须在同一次改动里登记到这里。

| 文档 | 负责什么 | 不写什么 |
|---|---|---|
| [research/astrbot-plugin-requirements.md](research/astrbot-plugin-requirements.md) | AstrBot 对第三方插件的硬性要求：元数据、生命周期、工具注册与权限、配置、依赖、数据目录、网络与代码规范 | 本插件自身的工具设计与实现方案 |
| [research/opencode-webfetch.md](research/opencode-webfetch.md) | OpenCode `webfetch` 工具的行为契约、分层实现、HTML→Markdown 能力边界、已知缺陷、TS→Python 迁移映射 | AstrBot 侧的取舍与实现决策 |
| [research/runtime-environment.md](research/runtime-environment.md) | 本插件的部署与运行环境事实：Docker 镜像、依赖安装路径、代理与网络 | 平台插件 API 约束 |
| [research/astrbot-hotfix-repository.md](research/astrbot-hotfix-repository.md) | 远程热补丁仓库的目录布局与清单字段 | 插件实现细节与发布流程 |
| [research/webui-mvvm.md](research/webui-mvvm.md) | 前端 Vue 的 MVVM 分层、目录约定与正反例 | 具体模块的业务设计 |
| [superpowers/specs/2026-10-26-web-fetch-design.md](superpowers/specs/2026-10-26-web-fetch-design.md) | `web_fetch` 工具的设计、契约、安全约束与验收标准（历史文档，只读） | 发布流程与仓库运营 |
| [superpowers/plans/2026-10-26-web-fetch.md](superpowers/plans/2026-10-26-web-fetch.md) | `web_fetch` 的分任务实现计划（历史文档，只读） | 设计取舍的理由 |
| [superpowers/specs/2026-10-26-toolkit-webui-design.md](superpowers/specs/2026-10-26-toolkit-webui-design.md) | 插件 WebUI「工具台」的界面结构、接口契约与验收标准 | 实现步骤与发布流程 |
| [superpowers/specs/2026-10-31-hotfix-loader-design.md](superpowers/specs/2026-10-31-hotfix-loader-design.md) | 远程热补丁加载器的清单格式、配置、注入/还原契约与验收标准 | 实现步骤、具体补丁内容 |
| [superpowers/plans/2026-10-31-hotfix-loader.md](superpowers/plans/2026-10-31-hotfix-loader.md) | 远程热补丁加载器与管理视图的分任务实现计划 | 设计取舍理由与发布流程 |
| [superpowers/plans/2026-10-26-toolkit-webui.md](superpowers/plans/2026-10-26-toolkit-webui.md) | 工具台的实现计划（历史文档，只读） | 设计取舍的理由 |

## 约定

- 每份文档开头用 HTML 注释声明「负责什么 / 不写什么」。
- 同一事实只写在归属文档，其他位置留一句加链接，不复制。
