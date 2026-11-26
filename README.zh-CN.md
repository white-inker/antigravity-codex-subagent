# Antigravity Codex Subagent

[English](README.md)

在 Windows 项目中，你可以让 Antigravity CLI 或 IDE 中的代理把任务交给 Codex，查看它的进度，在运行中补充指令，或在重启后继续同一段对话。Antigravity 代理通过官方 Python Codex SDK 发送消息。

## 准备环境

- 在 Windows 上安装 Antigravity CLI 或 IDE。
- 在 PowerShell 中确认可以运行 `git --version` 和 `python --version`。Python 需要 3.10 或更高版本。
- 为运行 Antigravity 的 Windows 用户配置 Codex 身份验证。如果已经在用 Codex CLI，可以运行 `codex login status` 查看登录状态。[Codex 身份验证文档](https://developers.openai.com/codex/auth)

## 安装技能

1. 在 PowerShell 中克隆仓库并进入项目目录。

   ```powershell
   git clone https://github.com/white-inker/antigravity-codex-subagent.git
   Set-Location -LiteralPath .\antigravity-codex-subagent -ErrorAction Stop
   ```

2. 运行安装脚本。如果手动改过已安装的技能或代理文件，请先保存自己的改动。

   ```powershell
   python manage.py install
   ```

   脚本会创建专用 Python 环境，安装指定版本的 SDK，并将当前用户的固定启动命令前缀写入已安装的技能。技能和代理文件位于 `%USERPROFILE%\.gemini\config`。看到 `Installation verified.` 表示脚本已成功查询本机会话历史。

3. 在 Antigravity 中打开这个仓库，新建对话以加载技能。

## 尝试只读任务

在新对话中告诉 Antigravity 代理：

> 用 Codex 以只读方式检查这个仓库，会话命名为 test-guide。哪个文件测试运行中插话？怎么运行这个测试？

Codex 应该会指出 `tests/test_steering.py`。等它回复后，继续问“这个测试在发送补充指令之前检查了什么？”，代理就会把追问发到原线程。如果需要 Codex 编辑文件，请说明允许修改的范围。你也可以在指令中指定模型和思考强度。

## 查看进度、插话或续接

| 什么时候 | 对 Antigravity 代理说 | 预期结果 |
| --- | --- | --- |
| 任务正在运行 | “Codex 查到哪里了？把最新的测试输出给我看。” | 代理读取原后台任务的日志，包括公开进度消息、命令、输出、退出状态和变动文件路径。 |
| 希望停止当前任务 | “停止当前 Codex 回合。” | 代理发出停止请求。原任务返回 `interrupted`（退出码 130）后，代理确认“已按你的要求停止”，并报告已经确认的文件改动。 |
| 需要调整正在进行的工作 | “再看一下，如果补充指令发出时原回合已经结束，会发生什么？” | `steer` 把指令发给活跃回合。`accepted` 表示 Codex 已接收，最终答复仍由原任务给出。 |
| 本轮已经结束 | “继续 test-guide，解释一下它怎么处理过期的回合 ID。” | `resume` 在同一个 Codex 线程中开启下一轮。 |
| 重启反重力，或从 CLI 切换到 IDE | “列出我的 Codex 会话，然后继续 test-guide。” | 代理从本机历史中找回原线程及其工作目录。 |

想连续聊天时，说“我要和 Codex 对话”。Codex 还没回复，你也可以继续发消息。代理用 `steer` 把新消息送入正在运行的回合。如果回合 ID 尚未出现，代理会告诉你消息正等待转发，并保留原文。上一轮结束后，再用 `resume` 在同一线程里续接。说“回来”即可退出转发模式，同时取消尚未发出的消息。

任务转入后台时，代理会告知已取得的 ID，在收到 Antigravity 的完成通知后报告结果。直接对话保留每条消息和答复的原文。需要翻译或摘要时请明确说明。委派任务时，代理可以单独补充相关背景。跨客户端续接时，两端应使用同一个 Windows 用户、同一个 Codex 历史目录（如果设置了 `CODEX_HOME`，两端的值应一致）以及原项目目录或工作树。

## 延续工作区权限

新会话默认只读。授权修改时，代理可以用工作区写入模式启动任务。脚本在线程创建时保存这个选择。如果第一轮启动失败，修好问题后，用原任务输出的线程 ID 重试即可，`resume` 会沿用已保存的权限。续接时显式切换模式，新回合启动后便会记住新的设置。没有权限记录的旧线程首次续接时需要明确选择一次。运行中插话沿用活跃回合的设置。

最终结果的 `changedFiles` 列出 SDK 确认已完成的补丁文件并去重，重命名包含新旧路径。Shell 命令产生的修改和失败时的部分改动需要另行核对工作区。主动中断会请求平稳停止，已经落盘的改动会保留。

## 维护安装

在 PowerShell 中进入克隆的仓库目录，再运行所需的命令。

| 任务 | 命令 | 预期结果 |
| --- | --- | --- |
| 更新技能 | `python manage.py update` | 以 `--ff-only` 拉取最新提交，安装并验证。新建 Antigravity 对话即可加载更新。 |
| 检查安装 | `python manage.py check` | 检查已安装的文件并查询本机会话历史。首次使用时，会话列表可以为空。 |
| 运行集成测试 | `python manage.py test` | 使用已安装的 SDK、临时 Codex 历史目录和本地模拟模型运行仓库中的测试。通过时显示 `OK`。 |

## 排查会话问题

- **找不到技能或专用 Python 环境。** 按[安装技能](#安装技能)中的命令获取仓库，在包含 `manage.py` 的目录运行 `python manage.py install`。安装后应有 `%USERPROFILE%\.gemini\config\skills\codex-delegate\scripts\.venv\Scripts\python.exe`，在同一目录运行 `python manage.py check` 应显示 `Installation verified.`。
- **找不到最近的会话。** 用 `--action list --workspace '.' --limit 1` 查找，取第一个匹配项。每页检查 20 个候选线程，每次调用最多检查 100 个，末页可能返回多个匹配。若结果为空且有 `nextCursor`，保留筛选条件，传入该游标继续查找。
- **提示线程仍在运行。** 这条追问还在等待转发。代理可以从原任务日志取得 ID，再用 `steer` 把追问发给正在运行的回合。
- **插话时找不到活跃回合。** 先查看原任务状态。如果已结束，用 `resume` 续接；如果仍在运行，切换到原任务日志里 `[codex] Working directory:` 后的规范目录，并使用同一份日志里的线程 ID 和回合 ID。进入该目录的子目录也会匹配到不同的管道。

- **Codex 提示登录。** 在同一 Windows 账号下运行 `codex login status`，未登录时运行 `codex login`。自定义 API 提供方应检查其凭据。`manage.py check` 验证的是本机会话历史访问。
- **找不到 Git。** 安装 Git for Windows，确认 `git --version` 可用；如果本次可以跳过仓库检查，新建时可传 `--non-git`。
- **模型或思考强度不受支持。** 查看报错中实际使用的模型和强度。切换模型时，可以显式指定新模型支持的 `--effort`，覆盖继承值。

每次对话中，代理在首次调用启动器前说明一次“始终允许”的范围。如果已知同一启动器此前调用时没有弹窗，就省略这句提示。如果为同时包含专用解释器和本项目 `codex.py` 的前缀选择“始终允许”，之后转发的消息和使用 `workspace-write` 的调用都可能直接执行。你也可以只批准当次调用。Codex 回合内部使用 `approvalPolicy: never`，需要更高权限时会报告受阻的操作。

PowerShell 调用示例、UTF-8 文件输入、历史分页和 JSON 输出字段见[技能说明](skills/codex-delegate/SKILL.md)。可选的 Antigravity 原生子代理窗口见[代理定义](agents/codex.md)。
