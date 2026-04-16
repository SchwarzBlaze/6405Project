# Study Lens Integrated

一个课后项目级别的 Windows 学习辅助程序，整合了两个已有 demo：

- `NLP6405-main`：桌面截屏、字幕条和基础 UI
- `lecture-lens-main`：讲座视频分析、报告生成和注释视频输出

当前版本已经统一为同一套推理方案：

- 桌面模式：`Windows Graphics Capture` + 本地 `llama.cpp server`
- 视频模式：讲座视频抽帧 + 本地 `llama.cpp server`

不再要求程序在 Windows 内部直接加载本地 Hugging Face Gemma 4。

## 当前支持

### 1. 桌面学习模式

- 选择一个目标窗口进行抓取
- 固定使用 `Windows Graphics Capture`
- 支持手动调节：
  - 采集间隔
  - 触发阈值
- 将截图缩放后发送给本地 `llama.cpp` 服务
- 返回结构化学术分析结果，并显示在主窗口和字幕条中
- 在主窗口中显示“当前送模截图”调试预览

### 2. 讲座视频模式

- 选择本地讲座视频
- 沿用 `lecture-lens` 的抽帧、分段、报告和注释视频输出能力
- 推理统一改为调用本地 `llama.cpp` 服务

## 推荐启动方式

### 1. 准备 Python 环境

```powershell
cd D:\codex工作区\6405project\study-lens-integrated
py -3.11 -m venv .venv311
. .\.venv311\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. 启动 llama.cpp 服务

推荐直接用官方建议的 Gemma 4 GGUF，并关闭 thinking：

```powershell
llama-server -hf ggml-org/gemma-4-E2B-it-GGUF --reasoning off
```

如果 `llama-server` 没进 PATH，也可以用完整路径：

```powershell
& 'C:\Users\mgavi\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe' -hf ggml-org/gemma-4-E2B-it-GGUF --reasoning off
```

启动后默认地址是：

```text
http://127.0.0.1:8080
```

程序里填写这个地址即可，程序会自动补成：

```text
http://127.0.0.1:8080/v1/chat/completions
```

### 3. 启动程序

```powershell
python .\main.py
```

## 使用说明

### 桌面模式

1. 先启动 `llama-server`
2. 打开程序
3. 在“llama.cpp 服务地址”里确认地址
4. 调整“采集间隔”和“触发阈值”
5. 刷新窗口列表
6. 选择要分析的目标窗口
7. 点击“启动桌面学习模式”

建议初始参数：

- 采集间隔：`0.10 ~ 0.20s`
- 触发阈值：`0.8 ~ 2.0`

如果你在 VS Code 里只是轻微滚轮滚动也想触发分析，优先把阈值调小。

### 视频模式

1. 保持 `llama-server` 运行
2. 点击“选择讲座视频分析”
3. 等待输出 `report.md` 和 `annotated_video.mp4`

## 关于窗口捕获

桌面模式当前不再做“区域截图 + 回退补丁”，而是固定使用 `Windows Graphics Capture`。  
这比简单裁剪桌面区域更接近 OBS 的单窗口捕获思路，也更适合你要的“稳定抓取特定窗口内容”。

## 目录结构

```text
study-lens-integrated/
|-- main.py
|-- launcher.py
|-- requirements.txt
|-- desktop/
|   |-- capture.py
|   |-- subtitle.py
|   `-- windows.py
|-- analysis/
|   |-- desktop_analyzer.py
|   |-- desktop_inference.py
|   |-- llamacpp_client.py
|   |-- video_pipeline.py
|   `-- video_worker.py
`-- video_core/
    |-- model.py
    |-- analyzer.py
    |-- slide_detector.py
    |-- audio.py
    |-- report.py
    `-- video_composer.py
```
