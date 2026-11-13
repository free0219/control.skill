# 本地管理
新专用目录为<项目>-control，重名加数字。新仓库main；已有独立仓库保持分支。Git身份沿用现有配置，缺失时询问，不伪造或改全局身份。
在项目根创建.control/project.json：
```json
{
  "schema_version": 1,
  "enabled": true,
  "mode": "local",
  "owned_workspace": false,
  "allow": ["AGENTS.md", "PROJECT_STATE.md", ".control/project.json", ".gitignore", ".agents/skills/control/**", "report.docx", "sources/**"],
  "deliverables": ["report.docx"],
  "remote": null,
  "cloud": {},
  "cloud_execution": {"enabled": false},
  "skill_version": "2.0.0",
  "completed": false
}
```
用真实路径替换示例。allow仅允许精确相对文件或末尾/**目录范围，不支持任意通配符或上级路径。只选项目必要范围。
mode为local/cloud，分别表示仅本地版本管理/启用云端推送（GitHub同步），与执行位置无关。remote为已核验无凭据GitHub HTTPS URL。branch记录实际目标分支，旧配置缺失时兼容当前分支；切换设备或云端checkout时不自动改写目标。cloud只放环境ID、聊天ID、入口和状态。owned_workspace仅新建专用目录为true，不构成删除授权。deliverables为最终文件精确路径。completed只在明确项目结束并验收后设true。
配置不包含凭据、个人绝对路径或完整聊天。
首次启用仅确定是否云端推送。cloud_execution.enabled默认为false；只有用户明确要求或同意云端执行才设true。cloud中的历史环境信息不等于启用授权；环境发布、当前实例验证、新任务恢复分别记录。云端执行失败不阻塞GitHub同步。
新增策略字段：`"policy": {"codex_changes": "auto_commit_and_sync", "manual_changes": "on_request", "cleanup": "explicit_request_only"}`。本地模式自动提交但不推送；启用云端推送时提交并同步。项目名称、仓库地址、分支、模式、主稿路径也写入PROJECT_STATE.md，使同目录新对话无需用户重发仓库链接。

复制本技能到项目.agents/skills/control；保留已有AGENTS.md并追加：
> 本项目已持续启用control.skill。修改任务开始先读.control/project.json、PROJECT_STATE.md及.agents/skills/control/SKILL.md。沿用模式，不重复询问启用或索取仓库链接。Codex产生修改后自动检查、定向提交，启用云端推送时自动同步；用户手动修改仅在用户要求同步或要求基于该文件继续修改时纳入。清理默认关闭，仅用户明确请求时按本次范围执行。未同步成功不得报告云端备份成功。

PROJECT_STATE.md保持简短：目标、约束、主稿、已完成、下一步、已知问题、验证结果、执行位置。不要写本次提交自己的哈希形成循环。

操作顺序：
1. 准备允许清单，忽略缓存、锁文件、依赖安装目录。新仓库git init -b main。
2. python <技能>/scripts/control.py --root <项目> inspect 检查文件和体积。
3. checkpoint --message "本轮实际修改" --paths 文件1 文件2 定向暂存并提交；只传本轮Codex修改及用户明确授权纳入的路径。失败检查标WIP。预先暂存的文件必须都归属本轮；不属于本轮时保留暂存区并先处理归属，不自动吸收。
4. 推送前inspect --history扫描所有可达历史；不符时保留原库，构建干净交接库，不能仅从当前树删掉文件就上传。

旧稿先保存版本再移除重复副本。恢复先导出旧提交预览；用户要求恢复主稿才替换并创建新恢复提交，不改写历史。
凭据启发式检查不能证明文件安全；首次仍判断用途。Word可能包含批注/修订，发现无关资料说明后处理，不静默破坏内容。

