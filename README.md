# 本地知识库问答 v2.0

2023 年写的第一个 AI 小项目，用 vibe coding 的方式整个重写了一遍。
对维基百科词条或本地文本做学习，建成 Chroma 本地向量库，
然后用文字或语音向 AI 提问，回答只依据知识库内容，并注明出处。

## 功能

- **知识学习**：输入中文维基词条自动抓取并学习；或上传本地 `.txt` 文件学习
- **向量知识库**：Chroma 本地存储，按句切块（约 1000 字，带 200 字重叠），每段记录来源词条与段号
- **文字问答**：先在向量库里找最相关的 3 段，再连同问题发给模型；库里没有相关内容就直接回答“我不知道”，不编造
- **语音问答**：对着麦克风说话，Gemini 转写后自动提问；回答可一键朗读
- **连续对话**：同一会话内保留最近 3 轮对话，可追问
- **带引用的回答**：每条回答下方标注来源，如“来源：海豹科 第 3 段”

## 快速开始

需要 Python 3.12 和一个 Gemini API key（去 Google AI Studio 申请）。

```bash
pip install -r requirements.txt
python main.py
```

首次运行会弹出设置框，填写 Gemini API key 后即可使用。
key 只保存在本机 `config.ini`，也可以用环境变量 `GEMINI_API_KEY` 代替；
`config.ini` 已加入 `.gitignore`，不会被提交到仓库。

也可以先复制模板再填：

```bash
cp config.example.ini config.ini
```

## 使用方法

1. 左侧输入维基词条（如“海豹科”），点“学习词条”；或点“上传本地 TXT 文件”
2. 学完后在右侧输入问题，点“发送”；或点“语音问答”直接说话
3. 打开“朗读回答”开关，回答生成后会自动朗读
4. 顶部“设置”可以改模型、取回段数和相似度阈值

注意：大陆访问中文维基百科需要可用的网络环境；词条不存在时会明确提示。

## 模型（2026-11-17 实测）

| 用途 | 模型 | 说明 |
| --- | --- | --- |
| 问答 | gemini-3.8-flash | 原计划的 gemini-2.5-flash 已不对新用户开放，API 建议用 3.8-flash |
| 向量 | gemini-embedding-001 | 原计划的 text-embedding-004 已下线，由 gemini-embedding-001 接替 |
| 语音合成 | gemini-3.8-flash-tts | TTS 只在 v1beta 提供，客户端固定走 v1beta |
| 语音转写 | gemini-3.8-flash（音频输入） | 录音经 Gemini 直接转写为文字 |

模型名都可以在设置里改。向量与 embedding 模型绑定：换向量模型后，
程序会把旧向量库自动备份为 `vs.bak-时间戳`，并重建空库，需重新学习词条。

## 工作原理

```
维基词条 / 本地 txt
  → 繁转简 → 按句切块（1000 字/段，200 字重叠）
  → Gemini 向量 → Chroma 本地库（vs/）
用户提问 → 向量检索 top 3（余弦距离 <= 0.45 才算相关）
  → 相关片段 + 问题 + 对话历史 → Gemini 回答（带引用）
  → 无相关片段 → 直接回答“我不知道”
```

## 项目结构

```
main.py              程序入口
ui.py                CustomTkinter 界面（浅色主题，1080x660）
gemini_client.py     Gemini 对话 / 向量 / 转写 / 合成
kb_store.py          Chroma 本地向量库封装
chunker.py           按句切块
wiki_client.py       中文维基百科抓取
voice.py             录音（静音检测）与放音
config_manager.py    config.ini 读写
config.example.ini   配置模板（空占位）
requirements.txt     依赖（已钉版本）
.github/workflows/   GitHub Actions：Windows 自动打包
legacy/v0.1-v0.2/    2023 年的老版本代码（仅作参考）
history/             示例知识库文本（马、猫、牛、奥迪）
wiki.txt             示例知识库文本（海豹科）
```

## 打包 Windows exe

### 方法一：GitHub Actions（推荐）

推到 `v2.0-rewrite` 或 `main` 分支后自动打包，
在 Actions 页面下载 `KB-QA-v2-windows`（内含 `KB-QA-v2.exe`）。
也可以在 Actions 页点 Run workflow 手动触发。
工作流文件见 `.github/workflows/build-windows.yml`，
全程不含任何 key。

### 方法二：本地打包（需要一台 Windows）

```bash
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --noconfirm --clean --onedir --windowed --name "KB-QA-v2" ^
  --icon app.ico --add-data "logo.png;." --add-data "config.example.ini;." ^
  --add-data "README.md;." --collect-all chromadb --collect-all onnxruntime ^
  --collect-all sounddevice main.py
```

打包完成后在 `dist\KB-QA-v2\KB-QA-v2.exe` 运行，
首次运行在设置里填 Gemini API key 即可。

## 安全说明

- 任何真实 key 只存在于本机 `config.ini` 或环境变量，绝不进代码和仓库。
- 语音在后台线程跑，界面不会卡住；异常会显示具体原因，不再只有一句“系统异常”。

## 版本记录

- **v2.0（2026-11-17）**：vibe coding 全面重写。模型全切 Gemini；
  系统版与客户端版合并为一个程序；模块化拆分；界面改为 CustomTkinter 浅色主题；
  新增引用来源、答不出就说不知道、连续对话、后台线程、具体报错；
  旧向量库不兼容，需重新学习。
- **v0.2**：去掉 LangChain，直接调 Chroma + OpenAI；提供客户端版（导入预建数据库 zip）。
- **v0.1**：初版，LangChain RetrievalQA + Azure OpenAI GPT-3.5 + Azure 语音。
