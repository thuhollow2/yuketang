"""答题异常告警。

用途单一：当"没有拿到可用的大模型答案"时，立刻在控制台、系统提示音、Windows 通知
三处同时提醒，并追加写入 data/alert.log。这样程序不会静默失败，也不会拿默认答案顶替。
"""

import base64
import os
import subprocess
import sys
import threading
import time
from xml.sax.saxutils import escape

current_dir = os.path.dirname(os.path.abspath(__file__))
home_dir = os.environ.get("YUKETANG_HOME", current_dir)
data_dir = os.path.join(home_dir, "data")
os.makedirs(data_dir, exist_ok=True)
alert_log = os.path.join(data_dir, "alert.log")

_BEEP_LOCK = threading.Lock()
_last_beep = 0.0
_last_toast = 0.0
_TOAST_INTERVAL = 5.0   # 秒，避免一次多题失败时刷屏

# Windows PowerShell 的 AppUserModelID，用它发通知，通知标题会显示为 Windows PowerShell
_PS_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"


def _beep():
    global _last_beep
    with _BEEP_LOCK:
        now = time.time()
        if now - _last_beep < 3:
            return
        _last_beep = now
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        return
    except Exception:
        pass
    try:
        sys.stdout.write("\a")
        sys.stdout.flush()
    except Exception:
        pass


def _ps_literal(text):
    """把字符串转成 PowerShell 单引号字面量。"""
    return "'" + str(text).replace("'", "''") + "'"


def _toast(title, body):
    """弹 Windows 通知。失败就算了，不影响主流程。"""
    global _last_toast
    with _BEEP_LOCK:
        now = time.time()
        if now - _last_toast < _TOAST_INTERVAL:
            return
        _last_toast = now
    if os.name != "nt":
        return
    xml = (
        '<toast><visual><binding template="ToastText02">'
        f'<text id="1">{escape(title)}</text><text id="2">{escape(body)}</text>'
        "</binding></visual></toast>"
    )
    script = (
        "$ErrorActionPreference='Stop';"
        "$null=[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime];"
        "$x=New-Object Windows.Data.Xml.Dom.XmlDocument;"
        f"$x.LoadXml({_ps_literal(xml)});"
        "$n=[Windows.UI.Notifications.ToastNotification]::new($x);"
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier({_ps_literal(_PS_APP_ID)}).Show($n);"
    )
    try:
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded],
            capture_output=True,
            timeout=15,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
    except Exception:
        pass


def alert(title, detail=""):
    """在控制台 + 声音 + 通知 + 文件四个地方同时告警。"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    bar = "=" * 64
    print(f"\n{bar}\n[{ts}] 答题告警: {title}\n{detail}\n{bar}\n", flush=True)
    try:
        with open(alert_log, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {title}\n{detail}\n{'-' * 64}\n")
    except Exception:
        pass
    _beep()
    try:
        threading.Thread(target=_toast, args=(title, (detail or title)[:160]), daemon=True).start()
    except Exception:
        pass


def format_reasons(errors, limit=3):
    """把 LLM 报错列表压成几行可读文本。"""
    if not errors:
        return "- 未记录到具体原因"
    lines = []
    for e in errors[:limit]:
        name = e.get("model") or e.get("name") or "-"
        detail = str(e.get("detail") or "").replace("\n", " ").strip()
        if len(detail) > 160:
            detail = detail[:160] + "..."
        lines.append(f"- {name}: {detail}")
    if len(errors) > limit:
        lines.append(f"- 另有 {len(errors) - limit} 条失败记录，见 data/alert.log")
    return "\n".join(lines)
