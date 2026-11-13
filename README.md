# control.skill

为单个项目提供本地 Git 版本管理、可选的 GitHub 私有备份及 Codex Cloud 接续流程。技能内部名称为 `control`。

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

- Codex 修改任务完成后定向提交；云端模式还会推送并核验。用户手动修改仅在指令授权时纳入。
- 云端准备由技能协调执行，受当前宿主工具和账户权限约束。只有实际验证成功才报告环境就绪或接续成功；上传仓库不代表云端环境已经建立。
- 清理默认关闭，仅在用户明确要求时处理本次授权范围。
- 技能是助手工作流程，不是后台监听服务。脚本的远端操作需要已授权的 GitHub CLI；其他可用工具按技能说明使用。

本公开仓库只分发技能；技能为用户项目创建的备份仓库默认私有。详细流程见 [SKILL.md](SKILL.md)。
