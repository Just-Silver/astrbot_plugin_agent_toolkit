<!-- 职责：前端 Vue MVVM 分层规则、目录约定与正反例；不写具体模块的业务设计。 -->

# 前端 MVVM 规范

## 分层

| 层 | 位置 | 职责 | 禁止 |
|---|---|---|---|
| Model | `webui/src/bridge.ts` | 桥接 AstrBot 视图 SDK、HTTP 请求、类型定义 | 持有 UI 状态 |
| ViewModel | `webui/src/viewmodels/use*.ts` | 业务状态、动作、调用 Model、错误处理 | 直接操作 DOM |
| View | `webui/src/components/*.vue` | 渲染、事件转发、i18n 文案 | 调 bridge、发请求、持有业务状态 |

`App.vue` 是容器：实例化 ViewModel，把 `vm` 传给对应 View，并负责模块切换。

## ViewModel 约定

- 一个功能一个 `use<Name>.ts`，返回 `reactive({ state, ...actions })`
- `state` 里放业务状态：列表、加载态、错误、表单值（若属于业务）
- 动作是普通 `async` 函数，内部调用 bridge，捕获异常并写入 `state.error`
- 派生值（已应用数量、是否可提交）由 ViewModel 计算并放进 `state`，或用 `computed` 后通过 `reactive` 返回
- 不依赖具体组件；同一个 ViewModel 可以被多个 View 使用

示例：

```ts
export function useHotfix() {
  const state = reactive({ status: null, loading: true, error: '' })
  async function load() { /* 调 bridge，写 state */ }
  return reactive({ state, load })
}
```

## View 约定

- 通过 `defineProps<{ vm: XxxViewModel }>()` 接收 ViewModel
- 模板只绑定 `vm.state.*`，交互直接调 `vm.action()`
- 纯展示子组件（如列表行）用 `props` + `emit`，不接收整个 vm
- 允许：`ref` 保存 UI 局部状态（展开哪些行、下拉是否打开）
- 禁止：`import { runFetch } from '../bridge'`

## 反例

```vue
<!-- 错误：View 直接请求并持有业务状态 -->
<script setup>
const result = ref(null)
async function submit() {
  result.value = await runFetch({ ... })
}
</script>
```

```vue
<!-- 正确：View 只绑定 ViewModel -->
<script setup>
const props = defineProps<{ vm: WebFetchViewModel }>()
</script>
<template>
  <NButton @click="vm.submit">{{ vm.state.loading ? '…' : '抓取' }}</NButton>
</template>
```

## 新增模块检查表

- [ ] 后端代码在 `modules/<name>/`
- [ ] ViewModel 在 `webui/src/viewmodels/use<Name>.ts`
- [ ] View 在 `webui/src/components/<Name>Panel.vue`
- [ ] `App.vue` 挂载模块入口
- [ ] View 文件里没有 `bridge` 的请求函数导入
