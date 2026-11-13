# control.skill

为单个项目提供本地 Git 版本管理、可选的云端推送（GitHub 同步）及云端执行（Codex 云环境）。技能内部名称为 `control`。

## 安装与换设备

需要 Git 和 Python 3.9+。在新设备上克隆到 Codex 的个人技能目录（如果设置了 `CODEX_HOME`，请使用其中的 `skills/control`）：

```powershell
git clone https://github.com/free0219/control.skill.git "$HOME/.codex/skills/control"
```

已有该目录时先检查并保留本地修改，不直接覆盖。对于从本仓库克隆且工作区干净的安装，可运行：

```powershell
git -C "$HOME/.codex/skills/control" pull --ff-only
```

在 Codex 中使用 `$control`，或说“这个项目做版本控制”。首次启用选择“仅本地版本管理”或“本地版本管理并启用云端推送”。

启用后的项目会保存自己的规则、状态和 `.agents/skills/control` 技能副本；接续该项目时读取仓库内副本，不依赖新设备上的个人技能安装。个人安装适合为其他项目启用技能。

## 工作方式

- Codex 修改任务完成后定向提交；启用云端推送时还会推送并核验。用户手动修改仅在指令授权时纳入。
- 云端推送只负责 GitHub 同步，不要求创建 Codex 环境。换设备可直接克隆/拉取项目，再读取项目内规则。
- 云端执行独立可选，仅在明确要求或同意后准备；当前实例验证、配置保存、环境发布、新任务恢复分别报告。执行受阻不阻塞独立的 GitHub 同步。
- 清理默认关闭，仅在用户明确要求时处理本次授权范围。
- 技能是助手工作流程，不是后台监听服务。脚本的远端操作需要已授权的 GitHub CLI；其他可用工具按技能说明使用。

本公开仓库只分发技能；技能为用户项目创建的备份仓库默认私有。详细流程见 [SKILL.md](SKILL.md)。

## 版本与验证

当前规则版本：2.0.0。旧配置 `mode=cloud` 继续表示云端推送，独立开关 `cloud_execution.enabled` 控制云端执行；缺失时默认为未启用。详见[升级说明](references/migration.md)。公开源库更新不会自动更新个人安装或项目技能副本，应检查差异并保留项目定制。

运行行为测试：`python -m unittest discover -s scripts -p "test_*.py" -v`。测试使用临时仓库，远端认证及 GitHub 响应使用模拟，不访问真实账号。
