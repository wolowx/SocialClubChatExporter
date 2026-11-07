# Social Club Chat Exporter

Windows 本地工具：把 Social Club 私信历史导出为 **HTML / TXT / CSV / JSON**。

只读取当前账号自己的消息，不发送、不删除、不上传任何数据。

## 准备工作

- Windows 10/11。
- GTA5 和 Social Club 面板能正常打开。
- 使用**旧版 Home 菜单**（工具依赖旧版 Social Club 面板）。

### 切换到旧版 Home 菜单

Steam 库 → 右键 `Grand Theft Auto V` → **属性** → **启动选项**，填入：

```text
-scDisableOverlayV3
```

保存后启动游戏。按 Home 打开的就是旧版 Social Club 菜单。

参考视频：<https://www.bilibili.com/video/BV1oTxR6jEE4/>

> 如果你按 Home 已经是旧版菜单，可以跳过这一步。

## 使用步骤

按顺序操作：

1. **先启动游戏**。
2. **打开工具** `SocialClubChatExporter.exe`。整个 `SocialClubChatExporter` 文件夹要一起保留，不能只拷 exe。
3. **安装证书**（仅首次）：点“安装证书”，确认。安装后如果工具提示，按 Home 关闭再打开一次 Social Club 面板。
4. **输入目标昵称**：在工具里填你要导出的人。
5. **开始监听**：点“开始监听”。
6. **回到游戏，按 Home** 打开 Social Club。
7. **点击“消息 / Messages”页签**。
8. **选择目标昵称的对话**。
9. **往下滚动，点击/继续加载历史消息**，直到看到最早的消息。
10. **回到工具**。
11. **点“停止并导出”**。

导出前工具会检查消息是否完整；确认完整后才保存。完成后可以点“打开输出文件夹”或“打开 HTML”。

## 小提示

- 打开 Home 后如果先出现别的会话，工具会**忽略它并继续等目标昵称**；匹配到目标才开始记录。
- 目标昵称留空时，工具会接受你打开的第一个会话，并在导出前让你确认。
- 只导出文字；附件、图片会忽略。
- 日志在 `%APPDATA%\SocialClubChatExporter\logs\exporter.log`，主界面点“打开日志文件夹”即可查看。
- 证书只安装到当前 Windows 用户，可在工具里卸载。
- 停止、出错或关闭工具时会恢复系统代理。

## 输出文件

默认保存在 `文档\SocialClubChatExport\<昵称>_<时间>\`：

- `<昵称>_chat.html`：可交互的聊天网页
- `<昵称>_chat.txt`：按时间排序的文本
- `<昵称>_chat.csv`：Excel 可直接打开
- `<昵称>_chat.json`：完整字段

## 从源码运行 / 打包

需要 Python 3.12 和 pip：

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m socialclub_exporter.app
```

打包成 Windows 程序：

```powershell
powershell -File build/build.ps1
```

输出：`dist\SocialClubChatExporter\SocialClubChatExporter.exe`

> 如果仓库没有附带 exe，可以按上面的命令自行打包，或从 Releases 下载（如果有）。
