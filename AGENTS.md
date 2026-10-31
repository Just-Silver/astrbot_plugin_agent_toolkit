<!-- 职责：项目级硬性约定与 agent 入口；不写具体功能设计与实现细节（见 docs/）。 -->

# 项目约定

## 前端必须使用 MVVM

Vue 前端**强制**遵循 MVVM。违反分层的代码不允许提交。

- **Model**：`webui/src/bridge.ts`，只负责与 AstrBot 视图桥接、HTTP 调用和类型定义
- **ViewModel**：`webui/src/viewmodels/use*.ts`，持有业务状态、调用 Model、暴露动作；用 `reactive` 返回给视图
- **View**：`webui/src/components/*.vue`，只接收 `vm`/`props` 并渲染，通过 `emit` 或调用 `vm` 的动作发起交互

**View 里禁止**：

- 直接 `import` 并调用 `bridge` 的请求函数
- 持有业务状态（表单以外的列表、加载态、错误态、领域数据）
- 写 `fetch` / `apiGet` / `apiPost` 逻辑

**View 里允许**：纯展示逻辑（展开/折叠、时间格式化）、i18n 文案。

新增功能模块时，一个模块对应：

```
modules/<name>/                 后端模块
webui/src/viewmodels/use<Name>.ts   ViewModel
webui/src/components/<Name>Panel.vue View
```

并在 `App.vue` 挂载。详细规则与示例见
[`docs/research/webui-mvvm.md`](docs/research/webui-mvvm.md)。
