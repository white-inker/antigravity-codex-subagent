# Codex Delegate

[English](README.md)

在提供终端的 Agent Skills 宿主中，可以使用同一个技能把本地任务交给 Codex。技能在 Windows、Linux 和 macOS 上通过官方 Python SDK 建立和续接会话，也支持查看进度、运行中插话和停止任务。

## 安装技能

1. 运行以下命令并选择你的 agent。全局安装可加 `--global`，也可用 `--agent <名称>` 直接选择。

   ```text
   npx skills add white-inker/codex-subagent --skill codex-delegate
   ```

   如果安装器没有对应选项，把整个 `skills/codex-delegate` 目录复制到宿主的技能目录。[Skills CLI](https://github.com/vercel-labs/skills) · [Agent Skills 规范](https://agentskills.io/specification)

2. 在已安装的技能目录中打开终端。需要带 `venv` 的 Python 3.10 或更新版本。Debian 和 Ubuntu 可能还需要安装 `python3-venv`。

   ```bash
   python3 scripts/setup_runtime.py install
   ```

   Windows 用 `python scripts/setup_runtime.py install`。脚本会安装指定版本的 SDK，成功读取本机会话历史后显示 `Installation verified.`。虚拟环境保存在技能目录之外。

3. 在运行 agent 的操作系统账号下登录 Codex。已经在用 Codex CLI 时，可用 `codex login status` 检查登录状态。重新加载宿主的技能，然后在对话里明确请 agent 使用 Codex。[Codex 身份验证文档](https://developers.openai.com/codex/auth)

## 尝试只读任务

在新对话中告诉 你的 agent：

> 用 Codex 以只读方式检查这个仓库，会话命名为 test-guide。哪个文件测试运行中插话？怎么运行这个测试？

Codex 应该会指出 `tests/test_steering.py`。等它回复后，继续问“这个测试在发送补充指令之前检查了什么？”，代理就会把追问发到原线程。如果需要 Codex 编辑文件，请说明允许修改的范围。你也可以在指令中指定模型和思考强度。

## 查看进度、插话或续接

| 什么时候 | 对 你的 agent说 | 预期结果 |
| --- | --- | --- |
| 任务正在运行 | “Codex 查到哪里了？把最新的测试输出给我看。” | 代理读取原后台任务的日志，包括公开进度消息、命令、输出、退出状态和变动文件路径。 |
| 希望停止当前任务 | “停止当前 Codex 回合。” | 代理发出停止请求。原任务返回 `interrupted`（退出码 130）后，代理确认“已按你的要求停止”，并报告已经确认的文件改动。 |
| 需要调整正在进行的工作 | “再看一下，如果补充指令发出时原回合已经结束，会发生什么？” | `steer` 把指令发给活跃回合。`accepted` 表示 Codex 已接收，最终答复仍由原任务给出。 |
| 本轮已经结束 | “继续 test-guide，解释一下它怎么处理过期的回合 ID。” | `resume` 在同一个 Codex 线程中开启下一轮。 |
| 重启宿主或切换客户端 | “列出我的 Codex 会话，然后继续 test-guide。” | 代理从本机历史中找回原线程及其工作目录。 |

想连续聊天时，说“我要和 Codex 对话”。回合 ID 出现后，代理用 `steer` 把新消息送入正在运行的回合。启动期间 ID 尚未出现时，代理会告诉你消息还没发出，可以稍后重发。上一轮结束后，用 `resume` 在同一线程续接。输入 `/codex-exit` 可返回当前 agent。

任务转入后台时，代理会告知已取得的 ID，在后台任务结束后报告结果。直接对话保留每条消息和答复的原文。需要翻译或摘要时请明确说明。委派任务时，代理可以单独补充相关背景。跨客户端续接时，两端应使用同一个操作系统账号、同一个 Codex 历史目录（如果设置了 `CODEX_HOME`，两端的值应一致）以及原项目目录或工作树。

## 延续工作区权限

新会话默认只读。授权修改时，代理可以用工作区写入模式启动任务。脚本在线程创建时保存这个选择。如果第一轮启动失败，修好问题后，用原任务输出的线程 ID 重试即可，`resume` 会沿用已保存的权限。续接时显式切换模式，新回合启动后便会记住新的设置。没有权限记录的旧线程首次续接时需要明确选择一次。运行中插话沿用活跃回合的设置。

最终结果的 `changedFiles` 包含 SDK 确认的补丁文件。可写回合在 Git 工作区中还会报告观测到的文件增删和修改，覆盖受跟踪和未被忽略文件中的 Shell 改动。`changeTracking` 标明覆盖范围。主动中断会请求平稳停止，已经落盘的改动会保留。

## 维护安装

用 Skills CLI 安装时，通过 `npx skills update codex-delegate --global` 更新，然后重新运行已安装技能的运行时初始化命令。项目安装用 `--project` 代替 `--global`。

从仓库安装时，在仓库目录运行以下命令。Linux 使用 `python3`。

| 任务 | 命令 | 预期结果 |
| --- | --- | --- |
| 更新技能 | `python manage.py update` | 以 `--ff-only` 拉取最新提交并更新源码目录使用的运行环境。 |
| 检查安装 | `python manage.py check` | 检查运行环境并查询本机会话历史。首次使用时，会话列表可以为空。 |
| 运行集成测试 | `python manage.py test` | 使用已安装的 SDK、临时 Codex 历史目录和本地模拟模型运行仓库中的测试。通过时显示 `OK`。 |

## 排查会话问题

- **找不到技能或专用 Python 环境。** 按[安装技能](#安装技能)重新安装。用已安装的 `scripts/setup_runtime.py` 执行 `check`，成功时会显示 `Installation verified.`。
- **找不到最近的会话。** 用 `--action list --cwd '<项目>' --limit 1` 查找，取第一个匹配项。若结果为空且有 `nextCursor`，保留筛选条件，传入该游标继续查找。
- **提示线程仍在运行。** 这条追问还在等待转发。代理可以从原任务日志取得 ID，再用 `steer` 把追问发给正在运行的回合。
- **插话时找不到活跃回合。** 先查看原任务状态。如果已结束，用 `resume` 续接；如果仍在运行，切换到原任务日志里 `[codex] Working directory:` 后的规范目录，并使用同一份日志里的线程 ID 和回合 ID。进入该目录的子目录也会匹配到不同的管道。

- **Codex 提示登录。** 在同一操作系统账号下运行 `codex login status`，未登录时运行 `codex login`。自定义 API 提供方应检查其凭据。`manage.py check` 验证的是本机会话历史访问。
- **找不到 Git。** 安装 Git，确认 `git --version` 可用；如果本次可以跳过仓库检查，新建时可传 `--non-git`。
- **模型或思考强度不受支持。** 查看报错实际使用的模型和强度。切换模型时默认使用配置值，也可以显式指定。保留当前模型时，用 `--effort default` 恢复默认强度。

只读和写入入口各有独立审批前缀，每个前缀都包含解释器及对应脚本路径。希望逐次审查时，可以对写入调用选择单次批准。升级后请移除旧 `codex.py` 入口的长期审批。Windows 使用命名管道，Linux 使用 Unix 套接字，控制入口只允许该回合所属的操作系统账号访问。

启动器调用示例、UTF-8 文件输入和 JSON 输出字段见[启动器参考](skills/codex-delegate/references/usage.md)。
