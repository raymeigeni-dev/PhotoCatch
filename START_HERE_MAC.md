# PhotoCatch — macOS 手动测试入口

本分支的单命令启动器用于打开现有 PhotoCatch 前端与本地 Flask API。它不会自动安装依赖，也不会关闭任何已经运行的进程。

## 一次性准备

在项目根目录执行（Python 3.11）：

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

如果本地已存在可用的 `.venv`，无需重复创建。

## 每次手动测试

```bash
bash scripts/launch_photocatch_macos.sh
```

启动器会：
- 检查 Python 依赖；
- 默认使用后端端口 5051 和静态前端端口 8000；
- 检查端口是否已占用，遇到占用就停止，不会杀死未知进程；
- 启动后端和前端服务器并轮询健康接口；
- 尝试自动打开浏览器；
- 将日志写入 `~/Library/Logs/PhotoCatch/backend.log` 和 `frontend.log`。

保持启动终端打开即可使用；按 Ctrl+C 会停止本次启动的两个服务器。

## 端口冲突时

不要结束 macOS 的 ControlCenter/AirTunes 进程。改用其他端口启动，例如：

```bash
PHOTOCATCH_BACKEND_PORT=5052 PHOTOCATCH_FRONTEND_PORT=8001 bash scripts/launch_photocatch_macos.sh
```

## 当前手动测试边界

先测试前端页面是否打开、摄像头/文件选择控件是否可用、视频初检是否返回可读报告，以及已有的 COLMAP 重建按钮是否明确报告成功或失败。真正的多视角网格重建仍需要本机安装并配置 COLMAP/OpenMVS；健康检查成功不代表重建成功。

苹果 Object Capture 的 Flask API 是实验性路径。若视频没有通过质量门槛，会返回 422；这不等于生成了模型。不要将其视为已验收的可用功能，除非真实视频已产出 USDZ 并经检查确认。
