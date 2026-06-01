# 配置说明

推荐用 YAML，因为 YAML 可以写真正的注释：

```powershell
Copy-Item examples\example.yaml config.yaml
notepad config.yaml
```

项目会优先使用 PyYAML；如果机器上没装 PyYAML，会自动使用内置的简单 YAML 解析器。
这个内置解析器足够读取 `examples/example.yaml`，但复杂 YAML 语法请安装 PyYAML。

## 最小手动验证码配置

```yaml
service:
  default_share_code: 你的默认邀请码

verification:
  source: manual

registration:
  email: your-email@example.com
  email_alias_mode: none
  max_attempts: 1
```

运行后，工具会在命令行里提示你输入邮箱验证码。

## Gmail Script 自动读验证码

`examples/example.yaml` 默认就是这个模式。你复制后只需要改两处：

- `verification.gmail_script_url`
- `registration.email`

```yaml
verification:
  source: gmail_script
  gmail_script_url: https://script.google.com/macros/s/xxxxx/exec
  poll_seconds: 600
  poll_interval_seconds: 5

registration:
  email: your-main-gmail@gmail.com
  email_alias_mode: gmail_dot
  gmail_max_dots: 3
  max_attempts: 3
```

`gmail_dot` 会自动生成 Gmail 点号别名。由于某些网站（如 Sousaku）会限制或封禁包含太多点号的邮箱（如 4 个及以上），本工具在生成点号别名时通过组合算法进行生成，并且你可以通过 `gmail_max_dots` 参数限制生成的别名中包含的最大点号数（默认值为 `3`）：

```text
your.main@gmail.com (1点)
y.ourmain@gmail.com (1点)
yo.ur.main@gmail.com (2点)
```

优先生成点号较少的“真实”邮箱，超过点号限制的会被自动跳过。

这些邮件都会进同一个 Gmail 收件箱。

## 可选项

- `browser.channel`: `msedge` / `chrome` / `chromium`
- `verification.source`: `manual` / `fixed` / `gmail_script`
- `registration.email_alias_mode`: `none` / `gmail_dot`
- `registration.gmail_max_dots`: 大于等于 0 的整数（默认为 `3`）
- `browser.keep_open`: `true` / `false`
- `webui.refresh_on_open`: `true` / `false`

`msedge` 和 `chrome` 会启动真实浏览器的无痕窗口，然后通过 CDP 接入。`chromium`
才是 Playwright 自带的自动化浏览器，主要用于调试。

## 奖励、NSFW、生成任务

`examples/example.yaml` 默认开启这些能力：

```yaml
preferences:
  enable_nsfw: true

generation:
  enabled: true
  wait_for_result: true
  publish_after_success: true
```

奖励任务及外部系统联动在 `chain` 下面配置：

```yaml
chain:
  # 被邀请者成功注册后，领取邀请人的任务奖励ID（大号拿邀请奖励）
  final_reward_task_id: task-times-new-user-unlock-rewards

  # 登录/注册成功后需要完成的可选社交媒体任务
  reward_task_ids:
    - task-times-community-twitter
    - task-times-community-discord

  # 登录/注册或生成任务完成后需要领取的奖励 ID 列表
  reward_claim_task_ids:
    - task-times-community-discord
    - task-times-community-twitter
    - task-times-create-first-image
    - task-times-create-first-video
    - task-times-share-first-published

  # 是否开启将获取到的 Plus 账号 Token 自动同步到 ProxyCanvas 项目中 (建议默认关闭 false)
  sync_plus_to_proxycanvas: false

  # 从 scripts/auto_token_tool/config.yaml 出发的相对路径
  # 示例：proxycanvas_config_path: ../../config/sousaku_config.json
  proxycanvas_config_path:
  # 示例：proxycanvas_server_port_path: ../../server_port.json
  proxycanvas_server_port_path:

  # 链式登录流程结束后，是否自动打开浏览器并登录最终成功升级为 Plus 的大号（推荐开启 true）
  open_final_plus_browser: true
```

图片/视频任务在 `generation.tasks` 里配置。每个任务保留网页抓到的 `endpoint` 和 `payload` 形状即可。

## 常用测试方式

```powershell
cd scripts\auto_token_tool
Copy-Item examples\example.yaml config.yaml
notepad config.yaml
.\test-sdk.bat
.\run.bat
```

`run.bat` 里选择：

```text
1. 单次登录
2. 链式登录
3. 查看账号
4. 启动 WebUI
```
