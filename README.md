# Antigravity Codex Subagent

在 Google Antigravity CLI 或 IDE 中，把任务交给 Codex。Gemini 通过 `codex.py` 调用官方 Python SDK。任务运行期间，Gemini 可以在同一个回合追加指令。关闭反重力后，也可以找回会话继续。

## 安装

需要 Windows、Python 3.10 或更高版本，以及已配置登录的 Codex 账号。在 PowerShell 中运行：

```powershell
git clone https://github.com/white-inker/antigravity-codex-subagent.git
Set-Location -LiteralPath .\antigravity-codex-subagent -ErrorAction Stop
$config = Join-Path $env:USERPROFILE '.gemini/config'
$skill = Join-Path $config 'skills/codex-delegate'
$scripts = Join-Path $skill 'scripts'
New-Item -ItemType Directory -Path "$config/agents", $scripts -Force | Out-Null
Copy-Item .\agents\codex.md "$config/agents/" -Force
Copy-Item .\skills\codex-delegate\SKILL.md $skill -Force
Copy-Item .\skills\codex-delegate\scripts\*.py, .\skills\codex-delegate\scripts\requirements.txt $scripts -Force
python -m venv "$scripts/.venv"
if ($LASTEXITCODE -ne 0) { throw 'Could not create the SDK environment' }
& "$scripts/.venv/Scripts/python.exe" -m pip install -r "$scripts/requirements.txt"
if ($LASTEXITCODE -ne 0) { throw 'Could not install the Codex SDK' }
& "$scripts/.venv/Scripts/python.exe" "$scripts/codex.py" --action list
```

安装会更新同名的 skill 和代理文件。打开新的反重力会话即可加载。早期版本使用的 `codex.mjs` 入口已迁移到 `codex.py`，已有 Codex 会话仍按原 `threadId` 续接。

## 使用

| 场景 | 对 Gemini 说 | 实际调用 |
| --- | --- | --- |
| 开始委派 | “用 Codex 查登录测试失败的原因，命名为登录修复。” | `new`，返回线程和回合 ID |
| 查看进度 | “Codex 查到哪里了？测试输出了什么？” | Gemini 用 `manage_task` 读取原后台任务的最新输出 |
| Codex 正在查 | “补充一下，只看令牌过期那条路径。” | `steer`，向活跃回合投递消息 |
| 本轮已完成 | “按刚才的结论修，补一个测试。” | `resume`，同一线程开启下一轮 |
| 重启或切换 CLI / IDE | “继续 Codex 的登录修复会话。” | `list` 找到原工作目录和线程，再续接 |
| 开启聊天 | “我要和 Codex 对话。”接着问“你是谁？” | 原样投递给 Codex，回传 SDK 的 `finalResponse` |

`steer` 通过 Windows 本地命名管道把消息交给正在运行的 SDK 进程，后者调用 `turn.steer()`。返回的 `accepted` 表示 Codex 已接收，最终答复仍由原后台任务给出。旧回合 ID 会被拒绝。指令在 Codex 下一次处理输入时生效，已执行的操作仍然保留。

运行期间，stderr 提供 Codex 的公开进度消息、命令与输出、退出状态和变动文件路径。stdout 在结束时返回一份 UTF-8 JSON，其中 `finalResponse` 是可直接转发的答复。

新建和续接可以指定 `--model`、`--effort` 和本轮允许的写入权限。运行中插话沿用当前回合的设置。CLI 和 IDE 应使用相同的 Windows 用户、Codex 历史目录和原工作树。每轮结果的 `usage` 可用来计算实际的 KV 缓存命中率。[OpenAI Prompt Caching](https://developers.openai.com/api/docs/guides/prompt-caching)

Gemini 实际执行的 PowerShell 命令和参数见 [SKILL.md](skills/codex-delegate/SKILL.md)。可选的原生子代理窗口使用 [codex.md](agents/codex.md)。

## 运行测试

完成安装后，在仓库根目录执行：

```powershell
$python = Join-Path $env:USERPROFILE '.gemini/config/skills/codex-delegate/scripts/.venv/Scripts/python.exe'
& $python -m unittest discover -s tests -v
```

集成测试使用临时 `CODEX_HOME` 和本地模拟模型，验证任务完成前能读到中文进度、向原回合插话，并在结束后恢复同一线程。
