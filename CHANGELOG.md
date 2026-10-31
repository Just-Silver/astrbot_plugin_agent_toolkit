# Changelog

<!-- 职责：记录每个基础版本的变更；不写设计理由与实现细节。beta 与正式版共用同一小节。 -->

## 0.3.0

### Added

- 远程热补丁模块 `modules/hotfix`：从 git 仓库拉取补丁清单，按用户选择注入 AstrBot 运行时，支持还原与刷新
- 补丁版本号与更新说明：发现新版本时不自动替换，继续运行已应用版本，由用户逐个确认更新
- 工具台内新增「模块」分组，热补丁作为独立模块入口
- 每个模块独立的界面组件：`WebFetchPanel.vue`、`HotfixPanel.vue`

### Changed

- 前端改为 MVVM 分层：Model `bridge.ts`、ViewModel `viewmodels/`、View `components/`
- 业务代码收进 `modules/`，插件根只保留 `main.py`

### Docs

- 新增根 `AGENTS.md`：MVVM 强制约定、提交与版本号规范、分支与发布流程
- 新增 `docs/research/webui-mvvm.md`、`docs/research/astrbot-hotfix-repository.md`

## 0.2.0

### Added

- WebUI 工具台：查看插件工具并直接测试 `web_fetch`
- 工具介绍与中英文 i18n

## 0.1.0

### Added

- `web_fetch` 工具：网页正文提取、大小与超时上限、SSRF 防护
