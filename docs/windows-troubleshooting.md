# Windows 部署排错记录

本文记录在 **Windows 11 + Python 3.12** 上从零部署本项目（`python main.py` 全链路：扫码登录 → 收题 → 大模型作答 → 提交）时实际踩到的问题，以及本 PR 中对应的修复。

按严重程度排序：前三条会直接导致程序跑不起来或提交错误答案，其余为可用性与可观测性问题。

---

## 一、启动即失败

### 1. `pyzbar` 导入失败：缺少 `msvcr120.dll`

**症状**

```
ImportError: Could not find module 'libzbar-64.dll' (or one of its dependencies).
Try using the full path with constructor syntax.
```

`util.py` 在模块顶层 `from pyzbar.pyzbar import decode`，导入失败会让 `python main.py` 连启动都做不到。

**原因**

`pyzbar` 依赖 ZBar 的 C 动态库，Windows 上的预编译轮子还依赖 **VC++ 2013 运行库**（`msvcr120.dll`）。很多干净的 Win11 环境没有装这个老运行库，于是 DLL 加载失败。

**修复**

- `util.py` 把 `pyzbar` 改为可选导入，并新增 `decode_qr_text()`，按 `pyzbar → zxing-cpp → opencv` 三级回退；
- 三条路都不可用时只打印提示，**不再抛异常**，二维码图片仍会保存到 `data/qr/`，可以手动扫码登录。

### 2. `zxing-cpp` 被「应用程序控制策略」拦截

**症状**

```
OSError: [WinError 4551] 应用程序控制策略已阻止此文件
```

**原因**

部分企业/学校下发的 Windows 会启用 WDAC / Smart App Control，未签名或信誉不足的二进制（`zxingcpp` 的 `.pyd`）会被直接拒绝加载。这类策略不是 pip 权限问题，`--user`、管理员运行都没用。

**修复**

回退链再加一层纯 Python/OpenCV 的实现：

```python
text, _, _ = cv2.QRCodeDetector().detectAndDecode(cv2.imread(path))
```

`opencv-python-headless` 走的是常见签名分发包，实测在本机策略下可以正常加载。

### 3. 控制台编码：中文乱码与 `UnicodeEncodeError`

**症状**

输出中文变成 `????`，或打印表情/特殊符号时抛出 `UnicodeEncodeError: 'gbk' codec can't encode character`。

**原因**

Windows 控制台默认代码页 936（GBK），Python 的 stdout 跟着走。

**修复**

新增 `start.bat`，启动前设置：

```bat
chcp 65001 >nul
set PYTHONUTF8=1
```

---

## 二、答案链路（最严重）

### 4. 拿不到大模型答案时，用「第一个选项」顶替

**症状**

模型超时、余额不足或 key 无效时，程序不报错，仍然提交了答案 —— 单选/多选/判断一律提交 A，填空提交空串，主观题提交空串。

**原因**

`answer_lesson()` 里有一段保底逻辑：

```python
if llm_answer:
    answer = llm_answer
else:
    if tp == 1: answer = [problems[...]['options'][0]['key']]
    ...
```

**影响**

这比「不作答」更糟：错误答案会被计入成绩，而且占掉了这次作答机会。

**修复**

删除整段默认兜底。拿不到 `llm_answer` 时直接 `return`，不发送任何请求，并通过告警通道提示原因与题干，交由人工作答。

### 5. 裸 `except: pass` 吞掉所有失败原因

**症状**

日志里只有「无答案」三个字，看不出是 401、超时、额度不足，还是返回格式不对。

**原因**

`LLMManager._generate_answer()` 的 `except: pass`，以及 `generateAnswer()` 里的 `if not self.answers: return reply`。

**修复**

- `_generate_answer()` 记录结构化错误：`{"model", "stage", "detail"}`，`stage` 区分 `config / empty / exception / parse / thread`；
- 返回体新增 `errors` 与 `missing` 字段；
- `yuketang.py` 把 `errors` 写入每道题的 `llm_error`，并汇总进告警。

现在一次失败的输出长这样：

```
原因:
- relay-gpt: HTTP 401: {"error":{"message":"invalid api key"}}
```

### 6. 考试全无答案时仍会发提交请求

**修复**

`submit_exam()` 先判断 `submitted_answer`：全空则直接返回并告警「不会提交空答案」；部分缺失时提示「已写入 N 题，剩余 M 题请自行补答」。

### 7. 提交结果没有校验

**症状**

接口返回业务错误（如 `msg != OK`、登录态过期）时，重试 3 次后静默退出，看起来像成功。

**原因**

```python
except:
    pass
```

**修复**

记录最后一次响应体与 `ok` 标志，失败时告警：

```
接口返回: {'msg': 'Authorization expired', 'code': 401}
处理: 请到课堂页面确认本题是否已作答。
```

### 8. `long.jpg` 过大导致中转站 400 / 502

**症状**

自建/中转 OpenAI 兼容接口返回 `400 Bad Request` 或 `502`，直连官方接口正常。

**原因**

`long.jpg` 是整节课 PPT 纵向拼接图，实测 3400 万像素、base64 后约 2.6 MB，超过不少中转站的请求体限制；同时视觉模型也无法从这种超长图里辨认题目。

**修复**

`generate_compatible_answer()` 在读图前先判断高度，`> 3000px` 时降级为纯文本作答（题干与选项文本本来就在 `query` 里）：

```
图片高度 4210px 过大，本次仅使用文本题干作答
```

### 9. 只能填固定厂商，无法用 OpenAI 兼容中转

**修复**

新增 `type: "compatible"`，`baseURL` 可配置，走标准 `/chat/completions`：

```json
{
    "name": "relay",
    "enabled": true,
    "type": "compatible",
    "baseURL": "https://your-relay.example.com/v1",
    "apiKey": "sk-...",
    "model": "gpt-4o-mini",
    "prompt": "You are a helpful assistant.",
    "temperature": 0.2,
    "score": 100
}
```

### 10. `an` 开、`llm` 关，静默无答案

**症状**

`lesson.an = true`、`lesson.llm = false` 时程序照常运行，但永远不答题，也没有任何提示。

**修复**

构造 `yuketang` 实例时检查组合并打印警告：

```
[main] 警告: lesson.an 已开启但 lesson.llm 未开启，题目不会自动作答（无答案来源）
```

---

## 三、可观测性

### 11. 失败没有任何提醒

程序通常挂在后台跑，只在终端打印，错过就错过了。

**修复**

新增 `alerting.py`，四路同时告警：

| 通道 | 说明 |
| --- | --- |
| 控制台 | 64 字符分隔线 + 时间戳，醒目横幅 |
| 声音 | `winsound.MessageBeep`，3 秒内去重 |
| Windows 通知 | PowerShell `ToastNotificationManager`，5 秒内去重，非 Windows 自动跳过 |
| 文件 | 追加写入 `data/alert.log` |

同时会把告警推送到已配置的钉钉/飞书/企微（`sendMsg(..., echo=False)`，避免控制台重复打印）。

### 12. `config.json` 没有示例文件

上游的 `config.json` 是被 git 跟踪的模板，用户填完真实 cookie / apiKey 后极易误提交。本 PR 新增 `config.example.json`（密钥统一用 `####` 占位），并建议本地执行：

```shell
git update-index --skip-worktree config.json
```

让 git 忽略你对 `config.json` 的修改。

---

## 四、验证方式

```shell
# 1. 依赖可导入（任一条不报错即可）
python -c "import util; print(util.decode_qr_text('data/qr/qrcode_main.jpg'))"

# 2. 大模型连通性（会打印耗时与原始返回）
python -c "from llm import LLMManager; print(LLMManager().generateAnswer('data/<domain>/lesson/<id>'))"

# 3. 错误 key 必须给出明确原因，而不是「无答案」
#    把 apiKey 改成非法值后运行 main.py，应看到 HTTP 401 与告警横幅

# 4. 缺答案时不得提交
#    关闭全部模型（enabled=false）运行，终端应出现：
#    「未取得大模型答案，已跳过提交」，且雨课堂页面没有新增作答记录
```

---

## 五、仍未覆盖的情况

- 二维码三级回退只在 Windows 上验证过；Linux/macOS 仍建议按 README 安装 `zbar`，走 `pyzbar` 主路径。
- Windows Toast 依赖 PowerShell 的 WinRT 投影，极简系统（如 Server Core、部分 LTSC）可能不弹通知，此时以 `data/alert.log` 为准。
- `long.jpg` 降级为纯文本后，纯图片题（题干本身就是图片）仍然拿不到答案，会走「跳过 + 告警」，不会瞎猜。
