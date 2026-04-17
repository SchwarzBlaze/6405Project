# Study Lens

Study Lens 是一个运行在 Windows 上的学习辅助程序，支持两种使用方式：

- 桌面学习模式：选择一个窗口，自动捕获页面变化并生成学习讲解
- 讲座视频模式：分析讲座视频，输出 Markdown 报告和带注释的视频

现在程序支持在界面中切换 `中文 / English`，切换后会影响：

- 主界面文字
- 悬浮窗提示
- 运行日志
- 桌面模式模型输出
- 视频模式模型输出
- 视频报告标题和部分说明文字

## 一键启动

如果你已经把 CUDA 版 `llama.cpp` 放到项目目录下的 `llama_cuda` 文件夹中，最方便的启动方式是直接双击：

- `start_study_lens.bat`

启动器会自动：

1. 检查本地 AI 服务是否已经在 `http://127.0.0.1:8080` 运行
2. 如果没有运行，就自动启动 `llama_cuda\\llama-server.exe`
3. 再自动打开 Study Lens 主程序

## 首次使用

### 1. 准备 Python 环境

```powershell
py -3.11 -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 2. 准备 CUDA 版 llama.cpp

请确认这些文件存在：

- `llama_cuda\\llama-server.exe`
- `llama_cuda\\ggml-cuda.dll`

### 3. 启动程序

直接双击：

```text
start_study_lens.bat
```

## 手动启动

### 1. 启动本地 AI 服务

```powershell
.\llama_cuda\llama-server.exe -hf ggml-org/gemma-4-E2B-it-GGUF --reasoning off -ngl all -c 8192 -np 1 -fa on
```

默认地址：

```text
http://127.0.0.1:8080
```

### 2. 启动主程序

```powershell
. .\.venv\Scripts\Activate.ps1
python .\main.py
```

## 桌面学习模式

1. 启动程序
2. 在顶部选择界面语言：`中文` 或 `English`
3. 确认 `AI 服务地址` 保持为默认值 `http://127.0.0.1:8080`
4. 点击“刷新窗口列表”
5. 选择需要分析的目标窗口
6. 按需调整：
   - `检测间隔`
   - `触发阈值`
7. 点击“启动桌面学习模式”

建议的起始参数：

- 检测间隔：`0.10 ~ 0.20s`
- 触发阈值：`1.0 ~ 2.0`

如果滚动页面后没有及时触发分析：

- 先把 `触发阈值` 调低
- 再把 `检测间隔` 调短

## 讲座视频模式

1. 保持本地 AI 服务运行
2. 选择界面语言
3. 点击“选择讲座视频分析”
4. 选中视频文件
5. 等待程序输出结果

分析完成后，输出目录中通常会包含：

- `report.md`
- `annotated_video.mp4`
- `frames/`

## 输出位置

默认输出目录是项目下的 `output` 文件夹。

每次分析视频时，程序都会自动新建一个带时间戳的子目录，方便区分不同结果。

## 常见问题

### 双击启动器没有反应

请检查：

- `.venv` 是否已经创建
- `llama_cuda` 文件夹是否存在
- `llama_cuda\\llama-server.exe` 是否存在

### 提示无法连接 AI 服务

请确认 `llama-server` 是否已经成功启动，并且地址仍然是：

```text
http://127.0.0.1:8080
```

### 视频右侧注释文字异常

请确认系统中存在可用字体，例如：

- 微软雅黑
- 黑体
- 宋体
