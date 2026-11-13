# 升级到2.0.0

配置schema_version保持1。mode=local只在本地提交；mode=cloud表示云端推送（GitHub同步），不再隐含Codex云端执行。remote、allow、deliverables、policy、owned_workspace及未知项目字段均保留。

新增skill_version="2.0.0"及cloud_execution={"enabled": false}。缺失cloud_execution时按未启用处理，不触发环境创建或发布。若当前对话/持久记录已有明确云端执行授权，可据此写true，无需重复确认；旧规则自动生成的环境待办或环境ID本身不是用户授权。

cloud对象及其历史信息原样保留；不删除环境、聊天或既有状态。补充当前验证结果时区分旧记录与新证据，不伪称已发布/已恢复。旧mode=cloud项目在没有环境、没有cloud字段、环境不可用时仍能同步GitHub。

branch可选；旧配置缺失时沿用当前分支，迁移时记录实际授权的目标分支。云环境可能检出work分支，不要凭名称自动把目标从main改成work。脚本向配置branch推送HEAD，验证同一目标引用；普通非强制推送仍保护远端历史。

更新项目副本：
1. 检查源库版本和项目git status，比较已有副本；保留定制和无关手动修改。
2. 同步SKILL.md、README.md、agents/openai.yaml、references/及scripts/中的分发文件，不复制.git、缓存或其他项目文件。定制有冲突时合并并运行测试，不覆盖。
3. 更新AGENTS.md和PROJECT_STATE.md中“云端推送必须准备环境”等旧要求，保留项目正文约束；写明实际采用版本和两项能力状态。不能把历史未验证结果改成成功。
4. 运行python -m unittest discover -s <项目技能目录>/scripts -p 'test_*.py' -v以及项目必要检查；定向提交本轮文件，按原配置同步GitHub。

源库、个人安装、项目副本是三个独立位置。源库推送成功不代表其他两处自动更新；报告本次实际升级的位置，其他设备下次拉取后生效。项目副本已有版本时可比对skill_version；不强制自动联网升级或覆盖项目定制。
