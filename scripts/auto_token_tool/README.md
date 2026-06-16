# auto-token-tool

`auto-token-tool` 是一个轻量级、配置驱动的 Python SDK，用于辅助浏览器自动获取 Token。默认示例针对类似 Sousaku 的邮箱登录。如遇人机验证（Cloudflare），浏览器会保持可见，以便手动完成验证。

---

## 快速开始

### 1. 环境准备
安装 Python 依赖及浏览器运行时：
```bash
python -m playwright install msedge chrome
```
拷贝并移动到项目根目录下，命名为 config.yaml，然后进行编辑：
```bash
copy examples\example.yaml config.yaml
```
根据需要修改 `config.yaml`（如 `registration.email` 及 `verification` 配置）。

## 邮箱与验证码模式

本工具支持两类常用邮箱来源：

### Gmail 主邮箱 + 点号别名

适合一个 Gmail 收件箱接收多个点号别名验证码。注册邮箱由 `registration.email`
生成，验证码通过 Google Apps Script 读取。

```yaml
verification:
  source: gmail_script
  gmail_script_url: "https://script.google.com/macros/s/AKfycb...你的部署ID.../exec"

registration:
  email: "your-main-gmail@gmail.com"
  email_alias_mode: gmail_dot
  gmail_max_dots: 3
  max_attempts: 3
```

### Outlook 卡片列表 + Microsoft Graph

适合使用一批 Outlook 邮箱。注册邮箱会从 Outlook 卡片文件逐个读取

```yaml
verification:
  source: microsoft_graph

registration:
  email_alias_mode: list
```

默认卡片文件路径是代码内置的 `data/outlook_cards.txt`。卡片文件每行一个邮箱卡片，格式如下：

```text
email@outlook.com----password----refresh_token----client_id
```

### 2. 方式 A：直接运行（免安装，以下方式二选一）
* **Windows 双击运行：** 直接运行根目录下的 `run.bat`，即可启动交互式菜单。
* **命令行手动运行：** 打开终端，执行以下命令：
  ```powershell
  # 设置 PYTHONPATH 指向 src 目录
  $env:PYTHONPATH="src"
  python -m auto_token_tool.cli
  ```

### 3. 方式 B：作为 SDK 集成
在你的 Python 项目中，将本项目的 `src` 目录加入路径后，直接调用接口：

```python
from pathlib import Path
import sys

# 从 ProxyCanvas 仓库根目录运行时，使用内置工具的相对路径。
AUTO_TOKEN_TOOL_SRC = Path("scripts/auto_token_tool/src").resolve()
sys.path.insert(0, str(AUTO_TOKEN_TOOL_SRC))

from auto_token_tool import AutoTokenTool

# 1. 初始化
tool = AutoTokenTool.from_file("scripts/auto_token_tool/config.yaml")

# 2. 单次登录
result = tool.login_once()
print(f"邮箱: {result.email}, Token: {result.account.token_masked}")

# 3. 链式自动注册（自动读取 Free 账号邀请码注册新账号并刷新）
# chain_result = tool.chain_login()
```

## Gmail 自动获取验证码 (Google Apps Script)

如果 `verification.source` 配置为 `gmail_script`，你需要部署一个 Google Apps Script 来作为验证码自动读取接口。

### 详细部署步骤：
1. 访问并登录 [Google Apps Script](https://script.google.com/)。
2. 点击左上角的 **新建项目 (New project)**。
3. 清空编辑器中的默认代码，复制并粘贴下面的完整脚本代码（已适配 10 分钟时效性过滤及防正则匹配时间戳机制）：

```javascript
function doGet(e) {
  var email = e.parameter.email;
  if (!email) {
    return ContentService.createTextOutput(JSON.stringify({error: "Missing email parameter"}))
                         .setMimeType(ContentService.MimeType.JSON);
  }

  // 获取 Python 传递过来的本次请求开始时间戳（毫秒）
  var minTimestamp = null;
  if (e.parameter.timestamp) {
    minTimestamp = Number(e.parameter.timestamp);
  }

  // 仅在普通收件箱中搜索（移除了 in:anywhere，同时去掉了 is:unread）
  var threads = GmailApp.search('to:"' + email + '" "Sousaku"');
  if (threads.length === 0) {
    threads = GmailApp.search('subject:"Sousaku"');
  }

  var code = null;
  var debugInfo = "";

  if (threads.length > 0) {
    var messages = threads[0].getMessages();
    var latestMessage = messages[messages.length - 1]; // 获取最新的一封邮件
    var msgDate = latestMessage.getDate();
    var now = new Date();

    // 判断邮件接收时间是否合规
    var isValid = false;
    if (minTimestamp) {
      // 允许 5 秒的系统时钟微小误差容限
      isValid = msgDate.getTime() >= (minTimestamp - 5000);
      debugInfo = "时间戳校验模式 -> 邮件时间戳: " + msgDate.getTime() + ", 允许的最早时间: " + (minTimestamp - 5000);
    } else {
      // 如果没传时间戳，默认判定 10 分钟内
      isValid = (now.getTime() - msgDate.getTime() < 10 * 60 * 1000);
      debugInfo = "10分钟时效校验模式 -> 邮件时间戳: " + msgDate.getTime();
    }

    if (isValid) {
      var body = latestMessage.getPlainBody();

      // 正则匹配 6 位数字验证码
      var match = body.match(/Your verification code is:[\s\S]*?(\d{6})/i);
      if (match) {
        code = match[1];
        latestMessage.markRead(); // 标记为已读，避免重复获取旧邮件
        debugInfo += " | 成功提取验证码: " + code;
      } else {
        debugInfo += " | 未能从正文中匹配到 6 位验证码";
      }
    } else {
      debugInfo += " | 最新的一封邮件发送于本次请求开始之前，已被安全过滤。";
    }
  } else {
    debugInfo = "未在普通收件箱中找到发送给 " + email + " 且包含 Sousaku 的邮件";
  }

  var response = {
    code: code,
    debug: debugInfo
  };

  return ContentService.createTextOutput(JSON.stringify(response))
                       .setMimeType(ContentService.MimeType.JSON);
}
```

4. 点击编辑器上方的 **部署 (Deploy)** 按钮，选择 **新建部署 (New deployment)**。
5. 在弹出的窗口中，点击齿轮图标，选择 **Web 应用 (Web app)** 类型。
6. 配置以下参数（**非常重要，配置错误会导致 Python 脚本报错无法访问**）：
   * **执行身份 (Execute as)**：选择 **我 (Me)**
   * **访问权限 (Who has access)**：选择 **所有人 (Anyone)**
7. 点击 **部署 (Deploy)** 按钮。
8. 首次部署时 Google 会弹出权限请求，点击 **授予访问权限 (Authorize access)**，选择你的 Gmail 账号，并允许其读取和管理邮件。
9. 部署完成后，拷贝弹出的 **Web 应用 URL**（以 `https://script.google.com/macros/s/.../exec` 结尾）。
10. 打开本地的 `config.yaml`，将该 URL 粘贴到 `verification.gmail_script_url` 配置项中。

### 11. YAML 配置文件修改示例
确保你本地的 `config.yaml` 文件的相关配置如下：
```yaml
# 1. 目标服务与邀请码配置
service:
  name: sousaku
  # 链式注册的初始邀请码（若本地没有可用账号，将使用此码作为起点，已修改为 QDFQS6）
  default_share_code: QDFQS6

# 2. 验证码获取配置
verification:
  # 验证码来源修改为 gmail_script
  source: gmail_script

  # 将第 9 步获取到的 Web 应用 URL 填入此处（用双引号包裹）
  gmail_script_url: "https://script.google.com/macros/s/AKfycb...你的部署ID.../exec"

  # 选填：最大轮询等待时间和轮询时间间隔（单位：秒）
  poll_seconds: 600
  poll_interval_seconds: 5

# 3. 账号注册配置
registration:
  # 必须填写！用于接收验证码的主 Gmail 邮箱地址
  # （如果启用了 gmail_dot 模式，自动生成的别名邮件也会进入该主邮箱的收件箱中）
  email: "your_email@gmail.com"

  # 邮箱别名模式（none = 仅使用主邮箱，gmail_dot = 自动生成带点号的 Gmail 别名，list = 读取 Outlook 卡片列表）
  email_alias_mode: gmail_dot

# 4. 外部项目同步联动（选填，默认关闭）
chain:
  # 是否开启自动同步获取的 Token 到 ProxyCanvas 项目
  sync_plus_to_proxycanvas: false

  # 【仅当开启同步时需要填写】ProxyCanvas 项目的配置文件路径：
  proxycanvas_config_path: ../../config/sousaku_config.json

  # 【仅当开启同步时需要填写】ProxyCanvas 项目的服务器端口文件路径：
  proxycanvas_server_port_path: ../../server_port.json
```

---

## 安全提示
* 请保护好本地生成的 `data/accounts.yaml` 和 `data/tokens.yaml` 文件，切勿提交至公开仓库。
* 如果使用 Outlook 模式，请同样保护好 `data/outlook_cards.txt`，其中包含邮箱、refresh token 和 client ID。
* 程序运行期间会在 `runtime/` 目录下生成浏览器的临时配置文件（如缓存、本地 Profile 等）。为了避免占用过多磁盘空间或彻底清理痕迹，**记得定期手动清理 `runtime/` 目录**。

## 免责声明

1. **用途限制**：本项目仅限协议建模、教学演示、授权安全研究和内部非商业验证，禁止用于任何商业用途、黑灰产服务、未授权目标或违反第三方服务条款的场景。
2. **责任自负**：一切法律、合规和安全责任由使用者自行承担。作者及贡献者对因使用本项目导致的账号限制、封禁、数据丢失或任何法律纠纷不承担任何直接或间接责任。
