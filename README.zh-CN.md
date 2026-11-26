# Antigravity Codex Subagent

[English](README.md)

在 Windows 项目中，你可以让 Antigravity CLI 或 IDE 中的代理 把任务交给 Codex，查看它的进度，在运行中补充指令，或在重启后继续同一段对话。Antigravity 代理通过官方 Python Codex SDK 发送消息。

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

   脚本会创建专用 Python 环境，安装指定版本的 SDK，并将技能和代理文件复制到 `%USERPROFILE%\.gemini\config`。看到 `Installation verified.` 表示脚本已成功查询本机会话历史。

3. 在 Antigravity 中打开这个仓库，新建对话以加载技能。

## 尝试只读任务

在新对话中告诉 Antigravity 代理：

> 用 Codex 以只读方式检查这个仓库，会话命名为 test-guide。哪个文件测试运行中插话？怎么运行这个测试？

Codex 应该会指出 `tests/test_steering.py`。等它回复后，继续问“这个测试在发送补充指令之前检查了什么？”，代理就会把追问发到原线程。如果需要 Codex 编辑文件，请说明允许修改的范围。你也可以在指令中指定模型和思考强度。

## 查看进度、插话或续接

| 什么时候 | 对 Antigravity 代理说 | 预期结果 |
| --- | --- | --- |
| 任务正在运行 | “Codex 查到哪里了？把最新的测试输出给我看。” | 代理读取原后台任务的日志，包括公开进度消息、命令、输出、退出状态和变动文件路径。 |
| 需要调整正在进行的工作 | “再看一下，如果补充指令发出时原回合已经结束，会发生什么？” | `steer` 把指令发给活跃回合。`accepted` 表示 Codex 已接收，最终答复仍由原任务给出。 |
| 本轮已经结束 | “继续 test-guide，解释一下它怎么处理过期的回合 ID。” | `resume` 在同一个 Codex 线程中开启下一轮。 |
| 重启反重力，或从 CLI 切换到 IDE | “列出我的 Codex 会话，然后继续 test-guide。” | 代理从本机历史中找回原线程及其工作目录。 |

想连续聊天时，说“我要和 Codex 对话”。说“回到 Antigravity 代理”即可结束转发。直接对话默认原样转交问题和答复，保留各自的语言。需要翻译或摘要时请明确说明。委派任务时，代理可以单独补充相关背景。跨客户端续接时，两端应使用同一个 Windows 用户、同一个 Codex 历史目录（如果设置了 `CODEX_HOME`，两端的值应一致）以及原项目目录或工作树。

## 维护安装

在 PowerShell 中进入克隆的仓库目录，再运行所需的命令。

| 任务 | 命令 | 预期结果 |
| --- | --- | --- |
| 更新技能 | `python manage.py update` | 以 `--ff-only` 拉取最新提交，安装并验证。新建 Antigravity 对话即可加载更新。 |
| 检查安装 | `python manage.py check` | 检查已安装的文件并查询本机会话历史。首次使用时，会话列表可以为空。 |
| 运行集成测试 | `python manage.py test` | 使用已安装的 SDK、临时 Codex 历史目录和本地模拟模型运行仓库中的测试。通过时显示 `OK`。 |

## 排查会话问题

- **找不到技能。** 在克隆目录运行 `python manage.py check`。如果提示文件或 SDK 环境缺失，运行 `python manage.py install`，再新建 Antigravity 对话。
- **某一页会话历史为空。** 每次查询最多从 20 个候选线程中筛选委派会话。如果还有 `nextCursor`，代理可以用这个游标和相同的工作区筛选条件继续查找。查询全部历史（`--all`）会跳过逐线程的来源检查。
- **提示线程仍在运行。** 让 代理读取原后台任务的进度。如果要改变方向，通过 `steer` 把补充指令发给当前回合。
- **插话时找不到活跃回合。** 先查看原任务状态。如果已结束，用 `resume` 续接；如果仍在运行，切换到原任务日志里 `[codex] Working directory:` 后的规范目录，并使用同一份日志里的线程 ID 和回合 ID。进入该目录的子目录也会匹配到不同的管道。

Windows 上每次启动脚本都直接请求在宿主环境运行，由当前权限策略决定是否确认。Codex 内层使用 `approvalPolicy: never`，包括 `workspace-write` 模式。需要更高权限时，代理会报告受阻的操作。

PowerShell 调用示例、UTF-8 文件输入、历史分页和 JSON 输出字段见[技能说明](skills/codex-delegate/SKILL.md)。可选的 Antigravity 原生子代理窗口见[代理定义](agents/codex.md)。
