# CCBD 人工测试问题台账

## 1. 目的

这个台账用于记录 `ccbd` 控制面人工测试过程中发现的问题，并把问题处理从“现象修补”约束为“根因收敛 + 系统性修复”。

记录原则：

- 不按零散症状打补丁
- 先固定最小复现，再判断问题边界
- 多个现象优先收敛到同一个根因
- 修复必须带回归测试或验收脚本更新

## 2. 处理流程

每个问题按下面顺序推进：

1. 记录现象
2. 固定最小复现
3. 确认失败层级
4. 找到 authority / state / lifecycle / read-path 的断点
5. 给出根因归类
6. 设计系统性修复
7. 增加回归测试
8. 复测并关闭

## 3. 根因分类

优先归到以下根因类别，而不是停留在表层症状：

- `bootstrap-contract`
  - 项目发现、`.ccb/config.yaml`、上下文建立不一致
- `identity-authority`
  - project identity / runtime authority / binding generation 不一致
- `daemon-lifecycle`
  - `ccbd` 启停、lease、socket、heartbeat、takeover 状态机不一致
- `runtime-supervisor`
  - start / stop / restore / reconcile 行为不一致
- `read-path`
  - `ps/ping/pend/logs/watch` 读路径与 authority 不一致
- `provider-facts`
  - provider 事实提取错误或 provider-specific 边界泄漏
- `mailbox-dispatch`
  - job / message / mailbox / reply 流转不一致
- `terminal-runtime`
  - tmux / pane / logs / runtime attach 事实不一致
- `compat-legacy`
  - 兼容层或旧 launcher / standalone askd 对主链路产生污染

## 4. 提报格式

人工测试时，尽量按下面信息发给我：

- 测试场景
- 执行命令
- 执行目录
- 预期结果
- 实际结果
- 关键输出
- 相关文件
  - 例如 `.ccb/ccbd/lease.json`
  - 例如 `.ccb/agents/<agent>/runtime.json`
- 是否稳定复现
- 复现频率

## 5. 问题列表

### ISSUE-001

- 状态：`fixed-retested`
- 标题：`ccb 在非 tmux 终端下遇到 stale binding 时输出启动成功，但没有真正打开 agent runtime`
- 根因分类：`daemon-lifecycle`
- 测试场景：`在项目根目录直接执行 ccb，当前终端不在 tmux 内，项目里保留旧 runtime/session binding`
- 最小复现：
  - 在项目根执行 `ccb`
  - 输出 `start_status: ok`
  - 随后 `ccb ps` 显示 agent 为 `degraded`
  - `tmux list-panes -a` 显示 `no server running`
- 预期结果：
  - `ccb` 应真正拉起可用 runtime
  - 若无法拉起，应明确失败，而不是输出成功
- 实际结果：
  - `start` 复用了 stale binding
  - `runtime.json` 保留旧 pane/session
  - health monitor 事后把 runtime 标记为 `degraded`
- 影响范围：
  - 所有 pane-backed provider
  - 所有不在 tmux 内执行 `ccb` 的启动路径
  - 所有残留旧 session/binding 的项目
- 初步判断：
  - `start` 路径把“存在旧 binding”误判成“可复用 binding”
- 根因：
  - `cli.services.runtime_launch.ensure_agent_runtime()` 在非 tmux 终端下被 `_inside_tmux()` 直接短路
  - 同时 stale binding 被原样返回给上层
  - `ccbd.start_flow` 继续把该 binding 写回 authority，导致 `start_status` 与真实 runtime 可用性脱节
- 系统性修复方案：
  - 移除 `ensure_agent_runtime()` 对“必须在 tmux 内”的前置限制
  - 允许直接走现有 detached tmux session/pane 启动链
  - 启动后若拿不到可用 binding，直接报错，禁止伪造成功
- 回归测试：
  - `test_ensure_agent_runtime_outside_tmux_relaunches_stale_binding_via_detached_session`
  - `test_ensure_agent_runtime_raises_when_launch_does_not_produce_usable_binding`
- 备注：
  - 这是 authority/lifecycle 契约错误，不是单个 provider 的适配 bug

### ISSUE-002

- 状态：`fixed-retested`
- 标题：`已有 .ccb 持久状态但缺失 config.yaml 时，ccb 会静默回填默认配置并错误重建项目启动面`
- 根因分类：`bootstrap-contract`
- 测试场景：`项目目录下已有 .ccb/agents 或 .ccb/ccbd 等持久状态文件，但 .ccb/config.yaml 丢失`
- 最小复现：
  - 构造 `.ccb/agents/demo/runtime.json`
  - 不提供 `.ccb/config.yaml`
  - 在项目根执行 `ccb`
- 预期结果：
  - `ccb` 应明确报错，要求恢复 `.ccb/config.yaml` 或清理旧状态
  - 不能把“已有状态的损坏项目”当成“空项目首次 bootstrap”
- 实际结果：
  - `start` 自动写入默认 `agent1/agent2/agent3` 配置
  - 随后直接拉起默认 agents
  - 原有 `.ccb/agents/demo/*` 状态被混入新的 project authority
- 影响范围：
  - 所有 v2 `start` 链路
  - 依赖相同 bootstrap 逻辑的 `ask_cli` / `ping_cli --autostart`
  - 配置文件误删、部分 checkout、手工迁移不完整等场景
- 初步判断：
  - 配置自动创建策略缺少“anchor 是否为空”的边界判断
- 根因：
  - `phase2`、`ask_cli.runtime`、`ping_cli.dispatch` 在上下文建立后无条件调用 `ensure_default_project_config()`
  - 该逻辑把“空 anchor 初始化”与“已有持久状态但配置丢失”混为同一类恢复动作
- 系统性修复方案：
  - 新增 `ensure_bootstrap_project_config()`
  - 只有当 `.ccb` anchor 中不存在任何持久状态文件时，才允许自动写入默认配置
  - 一旦 anchor 中已有状态文件，缺失配置必须直接失败并给出明确修复指引
- 回归测试：
  - `test_ensure_bootstrap_project_config_allows_empty_anchor`
  - `test_ensure_bootstrap_project_config_rejects_persisted_state_without_config`
  - `test_phase2_start_initializes_empty_existing_anchor`
  - `test_phase2_start_rejects_missing_config_when_anchor_has_persisted_state`
- 复测结论：
  - 黑盒复测确认：带 `.ccb/agents/demo/runtime.json` 且缺失 `config.yaml` 时，`ccb` 现在直接失败，且不会再生成默认配置

### ISSUE-003

- 状态：`fixed-retested`
- 标题：`未知 agent 或损坏 runtime.json 会阻断 kill/stop_all 清理路径`
- 根因分类：`read-path`
- 测试场景：`当前配置只包含 demo，但 .ccb/agents/legacy/runtime.json 仍残留旧版或损坏记录`
- 最小复现：
  - 配置 `demo:fake`
  - 额外保留 `.ccb/agents/legacy/runtime.json`
  - 执行 `ccb` 后再执行 `ccb kill -f`
- 预期结果：
  - `kill/stop_all` 应 best-effort 清理运行态
  - 未知 agent 目录或坏 runtime 记录不应阻断项目停止
- 实际结果：
  - `kill` 路径在读取额外 agent 目录时按 authoritative runtime 严格解码
  - 运行时抛出 `schema_version must be 2`
  - 项目无法正常停止
- 影响范围：
  - agent 改名、配置收缩、旧状态残留
  - `ccbd stop_all` 服务端路径
  - CLI 本地 fallback `kill` 路径
- 初步判断：
  - 清理路径把“配置 authority”与“磁盘残留扫描”混在了一起
- 根因：
  - `cli.services.kill` 和 `ccbd.supervisor.stop_all` 遍历 `.ccb/agents/*` 时，把所有目录都当作可严格解码的 runtime authority
  - 一旦遇到未知 agent 或损坏记录，清理流程直接中断
- 系统性修复方案：
  - 将“配置内 agent authority”与“额外目录 best-effort 扫描”拆开
  - 仅对配置内 agent 回写 stopped runtime
  - 对额外目录只做 best-effort runtime 读取与 pid/tmux 事实采集，不再让坏记录阻断清理
- 回归测试：
  - `test_kill_project_force_ignores_invalid_runtime_file_for_unknown_agent`
  - `test_runtime_supervisor_stop_all_ignores_invalid_runtime_file_for_unknown_agent`
- 复测结论：
  - 黑盒复测确认：存在 `.ccb/agents/legacy/runtime.json` 时，`ccb kill -f` 现在可正常返回 `kill_status: ok`

### ISSUE-004

- 状态：`fixed-retested`
- 标题：`HealthMonitor 会在缺少重绑证据时把 degraded runtime 误清为 healthy，导致后台恢复被短路`
- 根因分类：`runtime-supervision`
- 测试场景：`agent 已处于 pane-dead / pane-missing degraded 状态，runtime_ref 或 session 事实已丢失，系统进入 heartbeat`
- 最小复现：
  - 将 agent runtime 写成 `state=degraded`、`health=pane-dead`
  - 同时移除可直接验证的 pane binding
  - 执行一次 `ccbd heartbeat`
  - 随后观察 queue/start 行为
- 预期结果：
  - health monitor 只能“保留 degraded”或“基于证据恢复”
  - 不能在没有重绑成功的前提下把 runtime 清回 `healthy`
  - 后台 supervision loop 应继续接管恢复
- 实际结果：
  - `HealthMonitor._runtime_health()` 在 pane 检查返回空后，把任意非 healthy health 直接回写成 `healthy`
  - 这会让真正的 degraded runtime 脱离 supervision 目标集
  - 队列路径还能在没有有效 binding 的情况下继续启动 job
- 影响范围：
  - 所有 pane-backed provider
  - idle pane death 后的 heartbeat 自恢复
  - queue/start 对 degraded runtime 的准入判断
- 初步判断：
  - “健康归一化”逻辑越过了 authority/evidence 边界
- 根因：
  - `lib/ccbd/services/health.py` 将“没有进一步异常”错误等价为“已经健康”
  - 但在 degraded runtime 上，没有明确的 pane/session 重绑证据时，health 不应被自动清洗
- 系统性修复方案：
  - 保持 `HealthMonitor` 只负责检测和基于事实重绑
  - 对 `DEGRADED` runtime，若没有新的恢复证据，则保留原 health，不得自行清为 `healthy`
  - 新增 daemon-owned `RuntimeSupervisionLoop`，在 heartbeat 上对 configured agents 持续收敛 recoverable degraded runtime
- 回归测试：
  - `test_health_monitor_preserves_degraded_health_without_rebinding_evidence`
  - `test_runtime_supervision_loop_recovers_idle_degraded_agent`
  - `test_ccbd_heartbeat_recovers_degraded_agent_and_drains_queue`
- 复测结论：
  - 自动化复测确认：degraded health 不再被错误清洗
  - `heartbeat` 现在可以在 idle 场景下主动恢复 agent，并继续推进排队任务

### ISSUE-005

- 状态：`fixed-retested`
- 标题：`后台恢复缺少持久化 supervision authority，导致“恢复中/最近失败原因/daemon 代际”不可见`
- 根因分类：`runtime-supervision`
- 测试场景：`agent 在 heartbeat 中被后台恢复后，检查 .ccb/agents/<agent>/runtime.json 与 .ccb/ccbd/supervision.jsonl`
- 最小复现：
  - 将 agent 置为 `pane-dead`
  - 触发一次 `ccbd heartbeat`
  - 读取 `.ccb/agents/<agent>/runtime.json`
  - 读取 `.ccb/ccbd/supervision.jsonl`
- 预期结果：
  - runtime authority 应记录当前 daemon generation、desired_state、reconcile_state、last_reconcile_at、last_failure_reason
  - supervision log 应追加恢复开始/成功/失败事件
  - `kill/stop_all` 后 runtime authority 应落到 `desired_state=stopped`、`reconcile_state=stopped`
- 实际结果：
  - 旧实现只有瞬时内存行为，没有对应 authority 记录
  - 排障时无法区分“仍在恢复”“已经失败”“失败原因是什么”“是否属于当前 daemon generation”
- 影响范围：
  - 后台恢复排障
  - runtime authority 可解释性

### ISSUE-006

- 状态：`obsolete-contract`
- 标题：`旧设计曾尝试把 cmd 当作正常 caller mailbox owner，但该合同已废弃`
- 根因分类：`mailbox-dispatch`
- 测试场景：`旧方案曾允许在非 workspace agent 上下文执行 ask 时，sender 默认回落到 cmd，并期待 reply 进入 cmd mailbox`
- 最小复现：
  - 提交 `from_actor=cmd` 的 ask
  - provider 完成回复
  - 读取 `queue cmd` / `inbox cmd` / `ack cmd`
- 预期结果：
  - 当前合同下，`cmd` 不应作为 mailbox target 持久化
  - `ask` 默认 sender 应回落到 `user` 或真实 workspace agent
  - `queue/inbox/ack cmd` 应视为无效目标
- 实际结果：
  - 旧实现一度在部分 facade/control 路径上把 `cmd` 识别为 mailbox target
  - 这与更高层“cmd 不是正常 caller agent”的产品定位冲突，并放大 LLM 误判
- 根因：
  - 系统曾把“前台 pane 名称”和“正常 caller mailbox owner”两种身份混用
- 系统性修复方案：
  - `cmd` 仅保留为布局/前台 pane 名称
  - `cmd` 不再参与 sender 默认回落，也不再拥有 mailbox
  - reply mailbox 仅面向真实 agent mailbox owner
- 回归测试：
  - `test_dispatcher_rejects_cmd_sender`
  - `test_dispatcher_queue_summary_ignores_stale_cmd_mailbox_residue`
  - `test_ccbd_socket_rejects_cmd_sender`
  - `test_mailbox_store_rejects_cmd_mailbox_owner`
  - `test_mailbox_kernel_ack_reply_rejects_cmd_mailbox_owner`
- 复测结论：
  - 自动化复测应确认：`message_bureau`、`ccbd socket`、`ask_cli`、`ccbd dispatcher` 均不再将 `cmd` 视为正常 caller mailbox
- 初步判断：
  - supervision 行为和 authority 记录没有建模在一起
- 根因：
  - 缺少专门的 supervision event store
  - `AgentRuntime` 也没有承载 reconcile 元数据
- 系统性修复方案：
  - 为 `AgentRuntime` 增加 `daemon_generation`、`desired_state`、`reconcile_state`、`restart_count`、`last_reconcile_at`、`last_failure_reason`
  - 新增 `.ccb/ccbd/supervision.jsonl` 作为 append-only supervision 事件流
  - 在 heartbeat supervision loop 中先回写 `recovering`，再按结果回写 `steady/degraded`
  - 对连续失败的 recoverable degraded runtime 基于 `restart_count + last_reconcile_at + last_failure_reason` 执行 heartbeat backoff，避免恢复 thrash
  - 在 `kill/stop_all` 中将 configured-agent authority 收束到 `stopped/stopped`
- 回归测试：
  - `test_runtime_supervision_loop_recovers_idle_degraded_agent`
  - `test_runtime_supervision_loop_persists_failure_reason_and_event`
  - `test_kill_project_terminates_runtime_pid_files`
  - `test_agent_stores_roundtrip`
- 复测结论：
  - 自动化复测确认：recover 成功与失败都会持久化到 runtime authority 和 supervision log
  - 自动化复测确认：重复失败不会在每个 heartbeat 都再次触发恢复
  - `kill` 后 configured-agent runtime authority 现在会明确回到 stopped/stopped

### ISSUE-006

- 状态：`fixed-retested`
- 标题：`desired agent 缺失 runtime 时，heartbeat 不会自动补挂；直接复用 startup 事务还会误带 cleanup/layout 副作用`
- 根因分类：`runtime-supervision`
- 测试场景：`configured agent 的 runtime authority 丢失或进入 stopped/failed，然后进入 heartbeat`
- 最小复现：
  - 先让 agent 正常存在并入队
  - 删除 `.ccb/agents/<agent>/runtime.json` 或将其置为 stopped/failed
  - 执行一次 `ccbd heartbeat`
  - 观察 agent 是否自动恢复挂载，以及 tmux pane 布局是否被改动
- 预期结果：
  - daemon 应对 desired agent 自动补挂
  - mount 成功/失败应落到 runtime authority 和 supervision event log
  - 后台 mount 不应复用 startup cleanup 事务，也不应复用 interactive tmux layout
- 实际结果：
  - 旧实现只会恢复已有 degraded runtime，不会对 missing/stopped desired runtime 自动补挂
  - 如果简单复用 `run_start_flow`，还会把 startup 的 orphan cleanup 与 tmux layout 副作用带进 heartbeat
- 影响范围：
  - idle agent runtime 丢失后的自愈
  - desired agents 持续保持挂载
  - tmux 布局稳定性
- 初步判断：
  - 后台 supervision 和前台 startup 共享了启动能力，但没有分离事务副作用边界
- 根因：
  - supervision loop 之前没有 mount missing/stopped/failed desired runtime 的职责
  - `run_start_flow` 默认包含 startup 专属的 tmux orphan cleanup 与 interactive layout 行为
- 系统性修复方案：
  - 在 supervision loop 中新增 desired runtime mount 分支，对 missing/stopped/failed agent 执行 daemon-owned mount
  - mount 前写入 `starting` authority，mount 成功后收束到 `steady`，失败则落到 `failed`
  - 复用 `run_start_flow` 的启动链，但为后台 mount 显式关闭 `cleanup_tmux_orphans` 与 `interactive_tmux_layout`
  - mount 失败同样走 `restart_count + last_reconcile_at + last_failure_reason` backoff
- 回归测试：
  - `test_runtime_supervision_loop_mounts_missing_runtime`
  - `test_runtime_supervision_loop_persists_mount_failure`
  - `test_runtime_supervision_loop_applies_mount_failure_backoff`
  - `test_ccbd_heartbeat_starts_missing_agent_and_drains_queue`
  - `test_runtime_supervisor_start_can_skip_tmux_cleanup_and_layout_for_background_mount`
- 复测结论：
  - 自动化复测确认：missing desired runtime 现在会在 heartbeat 中被后台补挂
  - 自动化复测确认：后台 mount 会显式关闭 startup cleanup 与 interactive layout 副作用

### ISSUE-007

- 状态：`fixed-retested`
- 标题：`ccbd 崩溃后缺少项目级外部 keeper，导致后台只能等到下一次 ccb 命令才被动重启`
- 根因分类：`daemon-lifecycle`
- 测试场景：`项目已启动成功，ccbd 被外部 kill 或异常退出，然后观察后台是否会自行恢复`
- 最小复现：
  - 在带 `.ccb/config.yaml` 的项目里执行 `ccb`
  - 记录 `.ccb/ccbd/lease.json` 中的 `ccbd_pid`
  - 对该 pid 发送 `SIGTERM`
  - 等待 1 秒后重新读取 `.ccb/ccbd/lease.json`
- 预期结果：
  - 项目级 keeper 应自动拉起新的 `ccbd`
  - `lease.json` generation 应递增
  - `.ccb/ccbd/keeper.json` 应记录 keeper pid、最近检查时间与 restart_count
  - `ccb kill` 应先写 shutdown intent，再停止 keeper，且 kill 后不得反拉
- 实际结果：
  - 旧实现只有 `ensure_daemon_started()` 的“下次命令再重启”
  - `ccbd` 崩溃后项目会长时间处于 backend 缺失状态
  - 显式 kill 也没有外部 shutdown intent，可被外部保活逻辑误拉起
- 影响范围：
  - 所有项目 anchor 的后台保持
  - kill/shutdown 事务权威性
  - `lease.json` 的可解释性与代际追踪
- 初步判断：
  - “后台必须不保持死亡”这一条没有外部进程承接，因此 contract 只完成了一半
- 根因：
  - 缺少 project-scoped keeper 进程
  - `.ccb/ccbd/` 下没有 keeper state / shutdown intent 记录
  - `ensure_daemon_started()` 与 `ccb kill` 没有围绕 keepalive intent 建立闭环
- 系统性修复方案：
  - 新增 `.ccb/ccbd/keeper.json` 与 `.ccb/ccbd/shutdown-intent.json`
  - 引入 `ProjectKeeper` 作为唯一的 daemon keepalive 进程，只负责 `ccbd` 保活，不接管 runtime authority
  - `ensure_daemon_started()` 先清理 shutdown intent，再确保 keeper 运行
  - keeper 对 `missing/unmounted/stale` 与 `degraded unreachable` daemon 执行重启/接管
  - `ccb kill` 显式写入 shutdown intent，并等待 keeper 退出；必要时强制结束 keeper
  - `lease.json` 补充 `config_signature`、`keeper_pid`、`daemon_instance_id` 以提升可观测性
- 回归测试：
  - `test_project_keeper_spawns_missing_daemon`
  - `test_project_keeper_restarts_degraded_unreachable_daemon`
  - `test_project_keeper_stops_when_shutdown_intent_exists`
  - `test_ensure_daemon_started_waits_for_keeper_started_backend`
  - `test_shutdown_daemon_records_intent_and_terminates_keeper`
- 复测结论：
  - 黑盒复测确认：`ccbd` 被 `SIGTERM` 后，keeper 会自动拉起新 pid，且 generation 递增
  - 黑盒复测确认：`ccb kill` 后 `lease.json` 进入 `unmounted`，`keeper.json` 进入 `stopped`，且不会反拉
  - 黑盒复测确认：再次执行 `ccb` 会清除 shutdown intent，并重新建立 keeper + daemon

### ISSUE-008

- 状态：`fixed-retested`
- 标题：`服务端 stop_all 在 request_shutdown 后仍触发一次 mutating heartbeat，导致 kill 事务把刚停止的 desired agent 又补挂回来`
- 根因分类：`daemon-lifecycle`
- 测试场景：`项目已启动成功，执行 ccb kill 后检查 runtime authority 与 ps 输出`
- 最小复现：
  - 在 fake provider 项目中执行 `ccb`
  - 再执行 `ccb kill`
  - 读取 `.ccb/agents/<agent>/runtime.json`
  - 再执行 `ccb ps`
- 预期结果：
  - configured agent runtime authority 应落到 `state=stopped`
  - `desired_state=reconcile_state=stopped`
  - `ccb ps` 不应继续把 agent 显示成 `idle/partial`
- 实际结果：
  - backend 已经 `unmounted`
  - 但 runtime authority 仍被最后一次 heartbeat 改回 `idle / desired_state=mounted`
  - `ccb ps` 因此继续显示 agent 处于活动态
- 影响范围：
  - `ccb kill` 走服务端 `stop_all` 路径的所有场景
  - 显式 shutdown transaction 的 authority 收口
  - kill 后读路径一致性
- 初步判断：
  - shutdown intent 和 socket event loop 的 tick 时序不一致
- 根因：
  - `CcbdSocketServer` 把 `stop-all` 视为普通 mutating op
  - `stop_all` handler 调用 `app.request_shutdown()` 后，event loop 仍会执行一次 `on_tick()`
  - 该 heartbeat 触发 runtime supervision，再次把 desired agent 自动补挂
- 系统性修复方案：
  - 在 `CcbdSocketServer.serve_forever()` 中，当 handler 已经触发 stop_event/request_shutdown 时，跳过后续 mutating heartbeat
  - 增加 stop_all 集成回归，确保 kill 后 runtime authority 真正停在 stopped/stopped
  - 在启动/监督契约中明确：shutdown intent 一旦获取，不允许同一事务内再跑 remount heartbeat
- 回归测试：
  - `test_ccbd_stop_all_does_not_run_post_shutdown_heartbeat`
- 复测结论：
  - 黑盒复测确认：`ccb kill` 后 runtime authority 现在落到 `stopped/stopped`
  - 自动化复测确认：`stop_all` 不会再在 request_shutdown 之后触发补挂 heartbeat

### ISSUE-009

- 状态：`fixed-retested`
- 标题：`pane 被直接杀死时，HealthMonitor 先按 pid 缺失标成 orphaned，导致后台恢复和读路径都偏离真实 pane 状态`
- 根因分类：`runtime-supervision`
- 测试场景：`使用真实 pane-backed codex agent 启动项目后，直接 kill tmux pane`
- 最小复现：
  - 在临时项目执行 `ccb`
  - 记录 `.ccb/agents/demo/runtime.json` 中的 `pane_id`
  - 执行 `tmux kill-pane -t <pane_id>`
  - 等待 2-3 秒后读取 `runtime.json` 和执行 `ccb ps`
- 预期结果：
  - daemon 应优先依据 pane/session 事实执行恢复
  - 若 `ensure_pane()` 成功，runtime authority 应回写新的 pane/runtime facts
  - `ps` 应显示新的 pane，而不是旧 pane
- 实际结果：
  - 旧实现先检查 `runtime.pid`
  - pane 进程退出后先被打成 `health=orphaned`
  - supervision policy 不把 `orphaned` 当 recoverable，因此恢复链被短路
  - 即便后续由 session 层恢复成功，`pane_id/active_pane_id/pane_state` 也仍保持旧值，读路径显示漂移
- 影响范围：
  - 所有 pane-backed provider 在“pane 死亡伴随进程退出”的场景
  - `ccb ps` 对 pane 状态的可解释性
  - daemon heartbeat 对 pane death 的接管正确性
- 初步判断：
  - pid facts 与 pane/session facts 的优先级倒置了
- 根因：
  - `HealthMonitor._runtime_health()` 在 pane/session 检查之前就用 `pid_exists` 把 runtime 标成 `orphaned`
  - `HealthMonitor._rebind_runtime()` 只更新 `runtime_ref/session_ref`，没有同步 pane/runtime 元数据
- 系统性修复方案：
  - 将 pane/session 检查前置，只有在没有 pane/session 恢复信息时才回退到 `orphaned`
  - `HealthMonitor` 在 rebind/degraded 回写时统一同步 `pane_id`、`active_pane_id`、`pane_state`、`runtime_pid`、`session_file` 等 provider runtime facts
  - 在契约中明确：runtime pid 丢失只是 evidence，不能抢先覆盖 pane-backed recovery 决策
- 回归测试：
  - `test_health_monitor_prefers_pane_recovery_before_pid_orphaning`
  - `test_health_monitor_recovers_dead_tmux_pane_and_rebinds`
  - `test_health_monitor_preserves_last_binding_when_tmux_pane_missing_and_unrecoverable`
- 复测结论：
  - 真实黑盒复测确认：`codex` pane 被 kill 后，后台会恢复到新 pane，`runtime.json` 与 `ccb ps` 都会显示新 pane
  - 自动化复测确认：pid 缺失不再抢先把可恢复 pane death 归类成 `orphaned`

### ISSUE-010

- 状态：`fixed-retested`
- 标题：`keeper 拉起的 ccbd 在被 SIGTERM 后可能残留 zombie pid，导致恢复场景里旧 pid 长时间可见`
- 根因分类：`keeper-lifecycle`
- 测试场景：`运行中的 fake execution 期间直接 kill 当前 ccbd pid，等待 keeper 重启并恢复执行`
- 最小复现：
  - 启动项目并提交一个运行中的 fake provider 任务
  - 读取 `.ccb/ccbd/lease.json` 中的 `ccbd_pid`
  - 执行 `kill -TERM <ccbd_pid>`
  - 观察旧 pid 是否在 1-2 秒内真正消失
- 预期结果：
  - 旧 `ccbd` pid 应快速退出并从进程表消失
  - keeper 应随后重启新的 `ccbd`
  - 运行中的 execution 应由新的 daemon 恢复
- 实际结果：
  - keeper 是 `ccbd` 的直接父进程时，没有主动回收已退出子进程
  - 旧 pid 可能以 zombie 形式残留
  - 恢复测试因此卡在“旧 pid 仍存在”
- 影响范围：
  - keeper 管理下的 daemon crash/kill 恢复路径
  - 基于 pid 消失判断重启时序的黑盒测试
  - 进程表可解释性
- 初步判断：
  - 不是 daemon 没退出，而是 keeper 没有 wait/reap 已退出子进程
- 根因：
  - `ProjectKeeper` 会直接 spawn `ccbd`
  - 但 keeper 主循环中没有统一的 `waitpid(..., WNOHANG)` 回收逻辑
- 系统性修复方案：
  - 在 keeper 主循环中加入非阻塞 child reap，统一回收所有已退出直接子进程
  - 在诊断契约中明确 keeper 必须 reaping exited direct children
  - 保持恢复逻辑不依赖偶发的父进程退出或外部 init 回收
- 回归测试：
  - `test_reap_child_processes_drains_exited_children`
  - `test_ccb_fake_provider_recovers_running_execution_after_ccbd_restart`
- 复测结论：
  - 定向复测确认：旧 `ccbd` pid 在被 kill 后会在 keeper 循环内被回收
  - 自动化复测确认：running execution 的 daemon restart/recovery 用例恢复通过

### ISSUE-011

- 状态：`fixed-retested`
- 标题：`fresh namespace 的 cmd pane 先起真实 shell 再被 bootstrap respawn，导致启动后出现前导 % 或重复 prompt`
- 根因分类：`terminal-runtime`
- 测试场景：`项目彻底 kill 后重新执行 ccb，在 fresh project namespace 下观察 cmd pane 首屏`
- 最小复现：
  - 执行 `ccb kill`
  - 在项目根执行 `CCB_NO_AUTO_OPEN=1 ccb`
  - 执行 `tmux -S .ccb/ccbd/tmux.sock capture-pane -p -t %1 -S -20`
- 预期结果：
  - fresh namespace 的 `cmd` pane 首屏只出现一次干净 prompt
  - 不应出现前导 `%`
  - 不应出现启动阶段遗留的重复 prompt
- 实际结果：
  - 旧实现会先由 `tmux new-session` 启动一个真实交互 shell
  - 随后 `start_flow` 再对同一 pane 执行 `bootstrap_cmd_pane` / `respawn-pane`
  - 原始 shell 已经输出的 prompt 残留在 pane 内容里，zsh 在某些时序下会显示前导 `%`
- 影响范围：
  - 所有 fresh project namespace 创建路径
  - `ccb kill` 后首次重启
  - layout 重建后的 `cmd` pane 首屏一致性
- 初步判断：
  - 不是样式问题，也不是单纯 attach 输出串扰
  - 是 namespace 创建阶段“第一进程是谁”的生命周期契约错误
- 根因：
  - `ProjectNamespaceController._create_session()` 用 `new-session` 直接启动了真实交互 shell
  - `run_start_flow()` 又在 fresh namespace 上对 root/cmd pane 做二次 bootstrap
  - 因为第一次 shell 已经产生可见 prompt，后续 respawn 无法保证首屏无残留
- 系统性修复方案：
  - fresh namespace 的 root pane 初始进程改为静默占位进程，而不是交互 shell
  - `cmd` pane 仅在 layout 完成后执行一次正式 bootstrap，原地替换静默占位进程
  - 在启动监督契约中明确禁止“先起真 shell 再 respawn”为 `cmd` pane 建立首屏
- 回归测试：
  - `test_project_namespace_controller_uses_silent_server_commands`
- 复测结论：
  - 自动化复测确认：相关 project namespace / start flow / tmux cleanup 用例全部通过
  - 黑盒复测确认：`CCB_NO_AUTO_OPEN=1 ccb` 后 `%1` capture 只剩单个 prompt，不再出现前导 `%`

### ISSUE-012

- 状态：`fixed-retested`
- 标题：`ccb.config 变更后复用旧 namespace 并在 root pane 上继续局部 split，会让多列布局漂移`
- 根因分类：`terminal-runtime`
- 测试场景：`项目已存在旧 project namespace，随后增加 agents 或修改 .ccb/ccb.config 布局表达式，再执行 ccb`
- 最小复现：
  - 先以较小布局启动项目并保留 namespace
  - 修改 `.ccb/ccb.config`，例如从两列扩到三列
  - 再执行 `ccb`
  - 观察 pane 几何与 `ccb.config` 不一致
- 预期结果：
  - `ccb` 应根据新的可见布局整体重建 namespace，再重新投影 panes
  - 不允许在旧 pane 树上继续“补 split”来近似新布局
- 实际结果：
  - 旧实现只对本次 `launch_targets` 调用 `prepare_tmux_layout`
  - `prepare_tmux_start_layout()` 默认把传入 root pane 当成独占整个窗口
  - 在复用旧 namespace 时继续对 root pane 局部 split，会和旧 pane 树叠加，导致多列布局漂移
- 影响范围：
  - `.ccb/ccb.config` 变更后的前台重启
  - 新增 agents / 修改左右上下分组
  - 所有依赖 project namespace 复用的 tmux 布局启动路径
- 初步判断：
  - 不是单个百分比算法问题，而是“布局计划”和“namespace 复用判定”脱节
- 根因：
  - 系统缺少独立的可见布局计划层
  - namespace state 也没有记录当前可见布局签名
  - 因此启动链无法在布局表达式变化时做出“必须整体重建”的决策
- 系统性修复方案：
  - 新增独立布局计划模块，统一执行 `parse -> prune -> render`
  - 将规范化后的可见布局 render 作为 namespace `layout_signature`
  - foreground start 先比较期望 `layout_signature` 与当前 namespace state；不一致时强制 recreate namespace
  - `tmux_start_layout` 只消费布局计划，不再自行散落解析/裁剪逻辑
- 回归测试：
  - `test_build_project_layout_plan_preserves_three_column_layout_signature`
  - `test_build_project_layout_plan_prunes_subset_without_reordering_columns`
  - `test_project_namespace_controller_recreates_session_when_layout_signature_changes`
  - `test_runtime_supervisor_start_passes_visible_layout_signature_to_namespace`
  - `test_runtime_supervisor_background_mount_does_not_redefine_namespace_layout_signature`
- 复测结论：
  - 自动化复测确认：layout plan / project namespace / tmux start layout / supervisor 相关用例通过
  - 黑盒复测确认：当前项目三列两行配置 `cmd, agent1:codex; agent2:codex, agent3:claude; agent4:codex, agent5:gemini` 已按预期投影成三列布局

### ISSUE-013

- 状态：`open-planned`
- 标题：`真实 codex-cli 0.121.0 忽略 root-only 管理隔离，导致 agent 回复写入全局 Codex home 而 execution 无法完成`
- 根因分类：`provider-facts`
- 测试场景：`在 /home/bfly/yunwei/test_ccb 中由 agent1 ask agent2，agent2 实际回答但 ccb execution 长时间 running`
- 最小复现：
  - 在 `/home/bfly/yunwei/test_ccb` 启动项目
  - 配置包含多个 inplace Codex agents，例如 `agent1:codex` 与 `agent2:codex`
  - 执行 `agent1 ask agent2`
  - 观察 agent2 pane 已经输出答案 `2`
  - 检查 `.ccb/ccbd/executions/job_d06cdffcf34a.json`
- 预期结果：
  - agent2 的 Codex 日志应写入 agent2 私有 managed home
  - execution reader 应在 agent2 私有 home 内发现 `CCB_REQ_ID: job_d06cdffcf34a`
  - job 应完成并进入 reply 流程
- 实际结果：
  - `.ccb/ccbd/executions/job_d06cdffcf34a.json` 中 `log_path: null`、`session_path: ""`、`anchor_seen: false`
  - `.ccb/.codex-agent2-session` 只有 `codex_session_root`，没有绑定 `codex_session_id/codex_session_path`
  - `.ccb/agents/agent2/provider-state/codex/home/sessions/` 没有收到真实日志
  - 真实日志写到了 `/home/bfly/.codex/sessions/2026/04/19/rollout-2026-04-19T20-01-07-019da59d-ac36-7932-99ab-2b6801e160af.jsonl`
  - 该真实日志包含 `CCB_REQ_ID: job_d06cdffcf34a` 和最终答案 `2`
- 影响范围：
  - 使用真实 `codex-cli 0.121.0` 的 managed Codex agents
  - 多个 inplace Codex agents 共享同一 `work_dir` 的隔离正确性
  - 手动在项目目录运行 `codex` 时与 `ccb` managed Codex 的对话隔离
  - `ask` completion 读取、watchdog binding、restart resume
- 初步判断：
  - mailbox 通路正常，job 已入队并发送到 agent2
  - provider pane 正常执行并产生答案
  - 失败点在 managed Codex startup/session binding 与真实 CLI 日志落点不一致
- 根因：
  - 当前实现把 `CODEX_SESSION_ROOT` 当成默认 managed isolation authority
  - 实测 `codex-cli 0.121.0` 在只设置 `CODEX_SESSION_ROOT` 时仍把日志写入全局 `~/.codex/sessions`
  - 只有同时设置隔离的 `CODEX_HOME` 与 `CODEX_SESSION_ROOT` 时，真实 CLI 才把日志写入 managed provider-state
- 系统性修复方案：
  - 将 managed Codex 隔离单元从 session-root 级提升为 home 级
  - 每个 configured Codex agent 默认使用 `.ccb/agents/<agent>/provider-state/codex/home/`
  - `CODEX_SESSION_ROOT` 固定派生为 `<codex_home>/sessions`
  - 启动、恢复、completion reader、watchdog、diagnostics 全部以 managed home 为边界
  - 禁止通过扫描全局 `~/.codex/sessions` 修补 completion
  - legacy root-only session 只允许显式迁移，不允许作为长期运行模式
- 回归测试：
  - 待补：启动命令同时导出 `CODEX_HOME` 与 `CODEX_SESSION_ROOT`
  - 待补：两个 inplace Codex agents 拥有不同 managed homes
  - 待补：manual Codex in same work_dir 不会被 managed reader 采用
  - 待补：restart 后复用同一 managed `codex_session_id`
  - 待补：真实或 stubbed Codex 写到全局 home 时，execution 显示 managed-home violation 而不是永久 running
- 复测结论：
  - 待补

### ISSUE-014

- 状态：`open-observed`
- 标题：`restart 与并发 start 后，runtime/helper 代际与启动时间 authority 出现漂移`
- 根因分类：`identity-authority`
- 测试场景：
  - 在 `/home/bfly/yunwei/test_ccb` 执行 `start -> kill -> start`
  - 在 `/home/bfly/yunwei/ccb_test2` 对同一空 anchor 并发执行两次 `ccb`
- 最小复现：
  - `/home/bfly/yunwei/test_ccb`：
    - 执行 `/home/bfly/yunwei/ccb_source/ccb`
    - 执行 `/home/bfly/yunwei/ccb_source/ccb kill`
    - 再执行 `/home/bfly/yunwei/ccb_source/ccb`
    - 读取 `.ccb/ccbd/lifecycle.json`
    - 读取 `.ccb/agents/agent1/runtime.json`
    - 读取 `.ccb/agents/agent1/helper.json`
  - `/home/bfly/yunwei/ccb_test2`：
    - 对同一目录并发执行两次 `/home/bfly/yunwei/ccb_source/ccb`
    - 读取 `.ccb/ccbd/lifecycle.json`
    - 读取 `.ccb/agents/agent1/runtime.json`
- 预期结果：
  - restart 后新的 runtime/helper authority 应完整切换到当前 generation
  - `started_at`、`owner_daemon_generation`、`binding_generation` 应与当前 lifecycle / daemon generation 自洽
  - 同一项目并发 start 最终只能收敛为一套 generation，且不应留下“代际部分更新”的 authority
- 实际结果：
  - `/home/bfly/yunwei/test_ccb/.ccb/ccbd/lifecycle.json` 显示 `generation: 2`
  - 但 `/home/bfly/yunwei/test_ccb/.ccb/agents/agent1/runtime.json` 中新 `runtime_pid=4125663` 的同时，`started_at` 仍是上一代首次启动时间 `2026-04-22T00:37:35.631517Z`
  - `/home/bfly/yunwei/test_ccb/.ccb/agents/agent1/helper.json` 中新 `leader_pid=4125736`、`runtime_generation=2`，但 `started_at` 仍为上一代时间，且 `owner_daemon_generation` 仍为 `null`
  - `/home/bfly/yunwei/ccb_test2/.ccb/ccbd/lifecycle.json` 仍为 `generation: 1`
  - 但 `/home/bfly/yunwei/ccb_test2/.ccb/agents/agent1/runtime.json` 已出现 `binding_generation: 2`，同时 `daemon_generation: 1`、`runtime_generation: 1`
- 2026-04-22 继续复测：
  - `/home/bfly/yunwei/ccb_test2` 执行 `ccb kill -> ccb -> ccb ask agent1 "只回复：RESTART_OK"` 后，`doctor` 显示 `ccbd_generation: 3`
  - 但 `.ccb/agents/agent1/runtime.json` 变为 `binding_generation: 4`、`daemon_generation: 3`、`runtime_generation: 3`
  - `.ccb/agents/agent1/helper.json` 为 `runtime_generation: 3`、`owner_daemon_generation: 3`
  - 同目录下 `agent2`、`agent3` 也同样出现 `binding_generation: 4`、`daemon_generation: 3`
  - `/home/bfly/yunwei/test_ccb` 在正常 mounted 状态下未出现该偏差，`binding_generation/daemon_generation/runtime_generation` 仍保持 `5/5/5`
- 影响范围：
  - restart 后的 authority 可解释性
  - diagnostics / doctor 对“当前这条 runtime/helper 属于哪一代 daemon”的判读
  - 同项目并发 start 的代际一致性验证
- 继续观察：
  - 问题并非“所有项目必现”，更像是某些 restore/rebind 路径上仍存在单独推进 binding generation 的写回
- 初步判断：
  - 主生命周期本身能收敛，但 authority 写回存在“部分字段按新代更新、部分字段沿用旧代”的问题
  - 更像是 restart/rebind 路径的 authority 回写不完整，而不是实际重复拉起了第二套 backend
- 根因：
  - 待补
- 系统性修复方案：
  - 明确 runtime/helper authority 的字段归属：哪些字段属于“binding 重建”、哪些属于“daemon generation 切换”
  - 将 restart/rebind 回写收敛为单一 helper/runtime 更新入口，避免部分字段复用旧记录
  - 为 `started_at`、`owner_daemon_generation`、`binding_generation` 增加一致性断言与回归测试
- 回归测试：
  - 待补：`start -> kill -> start` 后 runtime/helper authority 全字段切换到新 generation
  - 待补：同项目双 `ccb` 并发时，最终 authority 不出现 `binding_generation > daemon_generation`
- 复测结论：
  - 待补

### ISSUE-015

- 状态：`fixed-retested`
- 标题：`kill 与新的 ask 并发时，ask 侧直接暴露 connection reset by peer`
- 根因分类：`daemon-lifecycle`
- 测试场景：`在 mounted 项目中并发执行 ccb kill 与 ccb ask agent1`
- 最小复现：
  - 在 `/home/bfly/yunwei/test_ccb` 保持项目 mounted
  - 并发执行：
    - `/home/bfly/yunwei/ccb_source/ccb kill`
    - `/home/bfly/yunwei/ccb_source/ccb ask agent1 "只回复：RACE_OK"`
  - 随后执行 `/home/bfly/yunwei/ccb_source/ccb doctor`
- 预期结果：
  - 新的 `ask` 应等待停机结果，或返回明确的 `shutting_down/project_unmounted` 类错误
  - 不应触发第二条启动链，也不应把底层 socket 断开原样泄漏给 CLI
- 实际结果：
  - `kill` 正常返回 `kill_status: ok`
  - 并发 `ask` 直接失败：`error: [Errno 104] Connection reset by peer`
  - 事后 `/home/bfly/yunwei/test_ccb/.ccb/ccbd/lifecycle.json` 维持 `generation: 2`、`phase: unmounted`
  - `doctor` 也显示没有生成新的 backend generation，说明没有发生双启动，但用户面暴露了未归一化的 socket 错误
- 影响范围：
  - `kill` 与 `ask` 并发的用户体验与可诊断性
  - keeper/shutdown fence 对前台 CLI 的错误语义稳定性
- 初步判断：
  - 停机收口本身是对的，但 CLI 与 daemon 之间缺少“正在停机”的显式协议化响应
- 根因：
  - 待补
- 系统性修复方案：
  - 在 shutdown intent 建立后，对新 `ask` 返回稳定的生命周期错误码，而不是底层 `ECONNRESET`
  - keeper / socket client 增加“stop in progress”判定与错误翻译
  - 为 `kill` 与 `ask` 并发增加黑盒竞态回归
- 回归测试：
  - 待补：`ccb kill` 与新的 `ccb ask` 并发时，`ask` 返回确定性错误且不产生新 generation
- 复测结论：
  - 2026-04-22 黑盒复测：在 `/home/bfly/yunwei/test_ccb` 并发执行 `ccb kill` 与 `ccb ask agent1 "只回复：RACE_OK"` 时，`ask` 不再暴露 `Connection reset by peer`
  - 当前稳定返回：`error: project ccbd is unmounted; run \`ccb\` first`
  - 事后项目保持 `unmounted`，且未观察到错误新 generation 产生

### ISSUE-016

- 状态：`open-observed`
- 标题：`keeper 在 daemon_boot 接管后推进 lifecycle generation，但 agent runtime/helper authority 仍停留在上一代`
- 根因分类：`identity-authority`
- 测试场景：`mounted 项目中直接强杀 owner_pid，让 keeper 走 daemon_boot 自恢复`
- 最小复现：
  - 在 `/home/bfly/yunwei/test_ccb` 保持项目 mounted
  - 读取 `.ccb/ccbd/lifecycle.json`，确认 `generation: 5`
  - 对其中 `owner_pid` 执行 `kill -9`
  - 执行 `/home/bfly/yunwei/ccb_source/ccb doctor`
  - 读取 `.ccb/ccbd/lifecycle.json`
  - 读取 `.ccb/agents/agent1/runtime.json`
  - 读取 `.ccb/agents/agent1/helper.json`
  - 再执行一次 `/home/bfly/yunwei/ccb_source/ccb`，确认是否自愈
- 预期结果：
  - keeper 接管后的新 daemon generation 应同步成为 agent runtime/helper authority 的当前代
  - 至少 `daemon_generation`、`runtime_generation`、`binding_generation`、`owner_daemon_generation` 应与 lifecycle generation 自洽
- 实际结果：
  - `doctor` 显示 keeper 已恢复项目，并进入 `ccbd_generation: 6`
  - `ccbd_startup_last_trigger: daemon_boot`
  - `.ccb/ccbd/lifecycle.json` 显示 `generation: 6`
  - 但 `.ccb/agents/agent1/runtime.json` 仍为 `binding_generation: 5`、`runtime_generation: 5`，只有 `daemon_generation` 被推进到 `6`
  - `.ccb/agents/agent1/helper.json` 仍为 `runtime_generation: 5`，仅 `owner_daemon_generation: 6`
  - 随后执行一次 `ccb` 返回 `ccbd_started: false`，上述 authority 仍不自愈
  - 同时 `ccb ask agent1 "只回复：AFTER_SIGKILL"` 可以完成，说明运行面可用，但 authority 已失真
- 影响范围：
  - keeper/daemon_boot 接管后的代际可解释性
  - diagnostics/doctor 对“当前 agent 是否属于当前 daemon generation”的判读
  - 后续基于 generation 的恢复、清理与一致性断言
- 初步判断：
  - keeper 接管只推进了 daemon/lifecycle authority，没有对已恢复 agent 的 runtime/helper authority 做同源回写
  - 这是 lifecycle 接管和 agent restore authority 之间的系统边界问题，不是单个 provider 执行失败
- 根因：
  - 待补
- 系统性修复方案：
  - 将 `daemon_boot` 接管后的 agent restore 统一走与正常 startup 相同的 authority 收敛路径
  - 禁止出现“lifecycle 属于新代、runtime/helper 仍属于旧代”的混合记录
  - 增加 keeper 接管场景下的 generation 一致性断言与黑盒回归
- 回归测试：
  - 待补：强杀 `owner_pid` 后 keeper 接管，runtime/helper/lifecycle generation 全量自洽
  - 待补：keeper 接管后重复执行 `ccb` 不会留下旧代 authority
- 复测结论：
  - 待补

### ISSUE-017

- 状态：`fixed-retested`
- 标题：`Codex session rebound 后 completion reader 仍盯旧日志，导致真实 ask 已回复但 job 不 terminal`
- 根因分类：`provider-facts`
- 测试场景：`Linux soak 中 kill/restart 后继续对 Codex agent 执行 ask 并观察 terminal convergence`
- 最小复现：
  - 执行 `CCB_LINUX_SOAK_SECONDS=90 CCB_LINUX_SOAK_KILL_EVERY=2 CCB_LINUX_SOAK_STUB_DELAY=0.2 CCB_LINUX_SOAK_ASK_WAIT_TIMEOUT_S=90 bash test/system_linux_soak.sh`
  - 在 kill/restart 后提交 Codex ask
  - provider stub 已在新 Codex session log 中写入 reply
  - execution polling 仍使用旧 session reader，terminal convergence 超时
- 预期结果：
  - restart/rebind 后 polling 应跟随当前 agent session binding
  - 新 session log 中出现 `CCB_REQ_ID`、assistant chunk、turn boundary 后，job 应进入 terminal
- 实际结果：
  - 回复已存在于新 Codex session log
  - dispatcher polling 没有切到新 log，导致 completion 丢失
- 影响范围：
  - Codex managed provider restart/rebind
  - kill/restart soak 后的 ask completion
  - daemon recovery 后 session file 被更新但 active submission reader 未更新的路径
- 根因：
  - `CodexProviderAdapter.poll()` 只使用 start 时构建的 reader
  - active submission runtime state 没有保存 workspace path，poll 时无法重新读取当前 session binding
  - session rebound 后旧 reader 的 preferred log 与当前 session log 不一致
- 系统性修复方案：
  - active / resume submission runtime state 保存 `workspace_path`
  - Codex poll 前读取当前 agent session binding
  - 若当前 session log 或 session id 与 reader/poll state 不一致，重建 reader 并从新 log 开始扫描
  - 不扫描全局 Codex home，不突破 managed session authority
- 回归测试：
  - `test_execution_service_codex_adapter_follows_rebound_session_binding`
  - focused codex adapter / tracker / socket suites
- 复测结论：
  - 2026-05-09 复测通过
  - `pytest -q test/test_v2_execution_service.py -k "codex_adapter"`：`10 passed`
  - `pytest -q test/test_v2_execution_service.py test/test_v2_completion_tracker.py -k "codex or protocol_turn or tracker"`：`15 passed`
  - 90 秒 Linux soak 与 5 分钟 Linux soak 均通过

### ISSUE-018

- 状态：`fixed-retested`
- 标题：`Linux soak / fastpath stress 脚本把健康输出或深队列任务误判为失败`
- 根因分类：`read-path`
- 测试场景：`真实 Linux soak 与 fastpath stress 使用 bash pipefail、grep -q 和固定 terminal convergence timeout`
- 最小复现：
  - 5 分钟 Linux soak 中 `doctor-20.out` 同时包含 `ccbd_state: mounted` 与 `ccbd_health: healthy`
  - 但脚本仍报 `doctor health` 失败
  - fastpath stress 中 60 个 ask 分摊到 3 个串行 provider，尾部 gamma job 未在固定 180 秒窗口内完成，脚本报 terminal convergence 失败
- 预期结果：
  - shell harness 不应因 `grep -q` 提前退出触发 `printf` SIGPIPE 而误判健康输出
  - fastpath stress 的 submit receipt 验证与深队列 terminal convergence 验证应使用不同预算
- 实际结果：
  - `set -o pipefail` 下 `printf '%s\n' "$out" | grep -q ...` 可能在大输出上因为 SIGPIPE 返回失败
  - 固定终端收敛等待预算小于 60 ask 深队列尾部 job 的真实串行收敛时间
- 影响范围：
  - Linux soak / stress 自动验收可信度
  - 对真实产品行为的误归因
- 根因：
  - 测试脚本把 shell 管道行为当成稳定观测原语
  - fastpath stress 同时验证 fast receipt 与 eventual convergence，但只配置了一个固定等待预算
- 系统性修复方案：
  - soak / stress 脚本统一使用 here-string `grep` helper，避免 `pipefail + grep -q` SIGPIPE 假失败
  - fastpath stress 默认根据 ask 数量、provider 数量和 stub delay 计算深队列 terminal convergence 预算
  - submit p95 仍使用独立毫秒阈值，避免把等待预算放大误当成 fastpath 放宽
- 回归测试：
  - `bash -n test/system_linux_soak.sh test/system_fastpath_stress.sh`
  - `bash test/system_fastpath_stress.sh`
- 复测结论：
  - 2026-05-09 复测通过
  - 5 分钟 Linux soak：23 轮、7 次 kill/restart，全部通过
  - fastpath stress：60 ask，submit p95 `227ms`，首/中/尾 terminal convergence、doctor、kill、unmounted 全部通过

## 6. 关闭标准

问题只有同时满足以下条件才关闭：

- 最小复现已稳定消失
- 根因已被明确，而不是仅屏蔽症状
- 至少新增或更新一条自动化回归
- 相邻主路径没有引入新的 fallback
- 人工复测通过
