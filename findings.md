# 诊断发现

## 用户症状

- 正在背诵题目、尚未进入考核阶段时刷新页面。
- 刷新后当前题目/背诵进度消失，需要重新进入并重新背诵。

## 发现

- 待调查。

- 前端测试使用 Node 内置测试运行器；`npm test` 已包含 `src/utils/sessionRecovery.test.js`。
- 与症状最相关的边界包括 `useMemorizeSession.js`、`stores/session.js`、`sessionRecovery.js` 和 `MemorizeFlow.vue`。
- 仓库已有“会话恢复”工具与测试，优先在该真实恢复 seam 上建立刷新前后状态断言。

- 源码将 `MEMORIZE_SHOW` 定义为 ACTIVE_STATES，理论上刷新应执行 restore。
- `session` Pinia store 使用 localStorage 键 `recall:session-snapshots` 持久化非 mock 快照。
- 实际运行的 `frontend/dist` 同时包含该 storage key 与 `MEMORIZE_SHOW`，且构建时间晚于相关源码修改；排除“运行旧构建包”假设。

- 路由使用 `createWebHistory`，刷新 `/memorize` 时应重新挂载 `MemorizeFlow` 并触发 `initSession`。
- 后端已有测试确认 `GET /api/sessions/{id}` 在展示态返回 `mode=memorize` 与 `state=MEMORIZE_SHOW`，排除响应缺少 mode/state。
- 现有测试只覆盖恢复决策纯函数，没有覆盖 Pinia 持久化 + 页面重新挂载 + API 对账的完整刷新链。

- localStorage 跨刷新持久化于 2026-08-23 16:53 的 `e016f58` 才加入。
- 2026-08-23 20:21 的 `3ba9406` 修复的是考核态 start_quiz 响应丢失后的重同步，不是展示态刷新。
- 当前症状位于展示态 `MEMORIZE_SHOW`，仍没有覆盖 store 重建与组件重新挂载的测试。

- 本地应用首页可正常加载，后端当前运行。
- 数据库中同时存在两个未完成的 `MEMORIZE_SHOW` 会话：#15 与 #16；这与“刷新/重新进入后新建一轮、旧一轮遗留”高度一致。
- 服务端并未删除刚才的题目，会话及 question_ids 仍在数据库；丢失发生在客户端恢复/关联环节。

- Vite 模块加载器下的 Pinia/localStorage 重建测试通过：展示态快照中的 sessionId、questions、quizzing=false 均能跨 store 重建保留。
- 首页 fresh token 明确使用 `String(Date.now())`，与路由读取的 string 类型一致，排除 token 类型不匹配。
- 剩余差异只存在于真实页面生命周期、浏览器存储可用性、origin 切换或 mock 快照策略。

- 后端支持用 `DATABASE_URL` 环境变量切换 SQLite；测试夹具明确规定临时库不得触碰真实 `data/bagu.db`。
- 决定：复制真实库到 `.tmp/refresh-repro/`，在 8011 端口启动隔离实例，用浏览器创建展示态会话并 reload 比对题目。

## 当前构建的刷新 E2E
- 隔离环境：临时数据库副本 + 127.0.0.1:8011 + 当前 dist。
- 展示态刷新前后 3 道题标题、顺序、URL、fresh 参数完全一致。
- 结果：PASS。当前构建无法复现用户症状；不是可用的红灯，因此不能据此声称代码根因已确定。

## 剩余排序假设
1. 旧标签页运行 localStorage 功能加入前的 bundle；首次刷新时旧内存快照无法迁移。
2. localhost:5173 与 127.0.0.1:8000 之间切换导致 origin 存储隔离。
3. 用户浏览器 localStorage 不可用/被清理；当前 store 静默降级到内存。
4. 当时是 useMock/offline 演示态，设计上不落盘。

## 继续入口红灯
- `npm test -- --test-name-pattern="记忆快照"` 已运行。
- 真实未完成快照与不可恢复快照两项断言均因 `store.canResumeMemorize === undefined` 失败。
- 该 getter 是首页是否展示继续入口的最小正确 seam。

## 继续入口实现
- `canResumeMemorize` 仅允许 sessionId 存在、未完成、非 mock 的快照。
- 新快照保存 mode；老快照无 mode 时继续按普通 memorize 兼容。
- 首页继续入口不携带 fresh，因此进入既有恢复链；“开始新一轮”仍生成 fresh。

## E2E 缓存校正
- 临时数据库确认会话已创建，页面题目与 DB question_ids 一致，不是 mock。
- 新生产 bundle `index-B9y9kTzs.js` 明确包含“继续上次记忆”。
- 首次 E2E 仍显示旧 CTA，原因候选为同一 8011 origin 复用了上一轮测试缓存；下一步用 cache-busting URL 强制加载新 index。

## 最终验证
- 全量前端测试：42/42 pass。
- 生产构建：Vite 84 modules，成功生成新 dist。
- 隔离 E2E：开始背诵 → 回首页 → 两个入口可见 → 继续 → 同三道题，PASS。
- 点击继续后 URL 为 `/memorize`，不含 fresh；临时库 id>15 会话数为 0，证明未新建会话。
- 首页视觉检查通过；两个按钮同排并可换行。
- 临时服务、浏览器页和 `.tmp/continue-memory-e2e` 均已清理。
