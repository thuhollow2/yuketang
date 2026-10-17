# Android APK 构建与发布

APK 使用 Chaquopy 运行仓库中的 Python 程序。当前默认版本为 `0.1.2`，
普通推送生成 `yuketang-helper-v0.1.2-debug.apk`；推送 `v0.1.2` 标签后，
还会在签名配置完整时生成并发布 `yuketang-helper-v0.1.2.apk`。

## GitHub 自动构建

工作流位于 `.github/workflows/android-apk.yml`，支持：

- 推送到 `main` 或 `master`：自动生成 debug APK。
- 在 Actions 中手动运行 **Build Android APK**：生成所选分支的 debug APK。
- 推送 `vX.Y.Z` 标签：debug 和 release 都使用标签中的版本；签名配置完整时，
  自动生成 signed release APK 并附加到同名 GitHub Release。

分支构建使用 `app/build.gradle` 中的默认版本。`versionCode` 按
`X * 1000000 + Y * 1000 + Z` 生成，`0.1.2` 对应 `1002`，高于旧版的 `1`；
`Y` 和 `Z` 的范围为 `0–999`。后续正式版本请递增标签，例如 `v0.1.3`，
同时更新默认版本，让分支构建的版本也保持一致。

### 发布 0.1.2

在仓库根目录检查本次改动后，使用以下 PowerShell 命令提交并推送。
下列列表覆盖本次 Android 设置、Python、示例配置及说明文档变更。

```powershell
Set-Location E:\yuketang\public\yuketang
git status --short
git add .gitignore app/build.gradle app/src/main/java/cn/yuketang/runner/MainActivity.kt app/src/main/python/android_entry.py app/src/main/python/config.json .github/workflows/android-apk.yml ANDROID.md llm.py yuketang.py config.json README.md
git diff --cached --stat
git commit -m "Release Android v0.1.2"
git push origin main
git tag v0.1.2
git push origin v0.1.2
```

先完成提交，再打标签，使标签包含本次全部改动。若 `v0.1.2` 已存在，
请使用下一个版本号并同步更新默认版本。

在 Actions 的构建记录中下载 `yuketang-debug-apk`；标签发布成功后，
也可在 Releases 下载正式 APK，或下载构建记录中的 `yuketang-release-apk`。

### 正式版签名条件

在 GitHub 仓库 **Settings → Secrets and variables → Actions** 中设置以下 Repository secrets：

| Secret | 内容 |
| --- | --- |
| `ANDROID_KEYSTORE_BASE64` | 正式签名 keystore 文件的 Base64 编码 |
| `ANDROID_KEYSTORE_PASSWORD` | keystore 密码 |
| `ANDROID_KEY_ALIAS` | 签名密钥别名 |
| `ANDROID_KEY_PASSWORD` | 签名密钥密码 |

后续升级必须继续使用同一份正式签名密钥。debug APK 与正式 APK 签名不同，
相互替换安装时可能需要先卸载；同签名且版本号递增的正式版可覆盖升级。

标签构建缺少任一 Secret 时，会在签名检查步骤明确失败，已上传的 debug APK 仍可下载。
普通分支的 debug 构建不需要这些 Secrets。Release 发布使用工作流自带的
`GITHUB_TOKEN`，工作流已声明 `contents: write` 权限。

## APK 中包含什么

构建任务会从仓库根目录同步 `main.py`、`yuketang.py`、`util.py`、`send.py`、
`llm.py`、`draw.py` 和字体 `msyh.ttc`，再与 `app/src/main/python` 合并打包。
因此，根目录 Python 代码提交后会进入新 APK；`README.md` 是仓库说明，无须打包。

APK 的初始配置来自 `app/src/main/python/config.json` 空模板。
根目录 `config.json` 和 `data` 不会打包到 APK。首次启动会在应用私有目录建立配置：

`/data/data/cn.yuketang.runner/files/yuketang/config.json`

用户在应用中配置账号；Cookie、二维码和课程文件存储在同目录的 `data` 子目录。

0.1.2 的模型预设与根目录示例配置同步，包含 DeepSeek。新配置的模型超时默认
为 300 秒；覆盖安装时保留已保存的设置，旧配置如需改为 300 秒，可在“全局配置”中修改。
新增或编辑账号、通知、模型时，点击弹窗外部不会关闭编辑。名单按班级名称填写，
上课时间表不允许保存同名班级条目（名称首尾空白会忽略）。

## 本地构建

使用 JDK 17 和 Android SDK，通过仓库自带的 Gradle Wrapper 构建：

```powershell
.\gradlew.bat :app:assembleDebug
```

产物为 `app/build/outputs/apk/debug/yuketang-helper-v0.1.2-debug.apk`。
Linux/macOS 使用 `./gradlew :app:assembleDebug`。正式签名版还需设置
`ANDROID_KEYSTORE_PATH`、`ANDROID_KEYSTORE_PASSWORD`、`ANDROID_KEY_ALIAS`、
`ANDROID_KEY_PASSWORD` 环境变量，再运行 `:app:assembleRelease`。

最低支持 Android 7.0（API 24），包含 `arm64-v8a` 和 `x86_64`，
Python 程序在 Android 前台服务中运行。
