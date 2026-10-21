# PhotoCatch — 摄像头检测与实验性 3D 网格预览

PhotoCatch 是一个本地运行的实验性原型：通过摄像头抓取单帧，调用本地 Flask 后端检测候选区域，再把选中区域的二维轮廓沿深度方向挤出为三角网格，并在浏览器中交互预览。

> **能力边界：** 当前检测器基于 MediaPipe Hands、Pose 与 Selfie Segmentation，并非通用物体检测器。代码中的检测 confidence 数值目前是固定常量，不是经过校准的模型置信度，不能用于严肃的准确率判断。当前 3D 算法是单张图像的轮廓挤出，不是多视角摄影测量，也不会恢复真实背面、真实深度或可靠的物理尺寸。结果适用于原型验证，不应宣传为完整的真实物体 3D 扫描。

## 当前功能

- 本地 Flask API：健康检查、候选区域检测、ROI 网格生成。
- 视频导入（MP4/MOV 等）、时间分布抽帧、清晰度/亮度/特征匹配初检和代表帧预览。
- 摄像头捕获、候选区域选择和 API 错误提示。
- Three.js 交互式网格预览：拖动旋转、滚轮缩放。
- 导出当前网格为 JSON。
- 输入校验和后端自动化测试。
- GitHub Actions 自动运行 Python 测试。

## 环境要求

- Python 3.11（CI 使用版本；建议本地也使用 3.11）
- 可访问摄像头的现代浏览器
- 本地依赖安装需要网络
- 浏览器需支持 WebGL；摄像头一般要求 localhost 或 HTTPS
- 前端当前从 jsDelivr 加载 Three.js，因此首次使用预览需要浏览器网络访问该 CDN

## 启动（macOS / Linux）

在仓库根目录执行：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m backend.server
```

后端默认监听 `http://127.0.0.1:5000`。若你已有环境，也可以按原有方式启动，但请确保启动的是当前 checkout 的代码。

另开一个终端，在仓库根目录启动静态前端服务器：

```bash
python -m http.server 8000
```

浏览器打开：

```text
http://127.0.0.1:8000/frontend/index.html
```

允许摄像头权限，点击“启动摄像头” → “检测当前帧” → 选择候选区域 → “为所选区域生成 3D”。后端地址默认是 `http://127.0.0.1:5000`。如需指定其他 API 地址，可在 URL 中加入 `?api=http://127.0.0.1:5001`（仅限可信的本地服务）。

## 自动化测试

```bash
python -m pytest -q
```

测试覆盖工具函数、API 输入校验、网格拓扑不变量、凹多边形三角剖分，以及前端入口文件和关键控件的静态冒烟检查。静态前端测试**不等于**真实浏览器端到端测试；真实摄像头、WebGL 渲染与不同设备兼容性仍需实际运行验收。

## API

- `GET /api/health`
- `POST /api/video/analyze`：multipart/form-data，字段名 `video`；提取最多 24 帧并返回清晰度、亮度、ORB 特征匹配启发式指标及预览帧。初检不是重建结果，也不能单独证明相机运动或 SfM 可解。
- `POST /api/detect`：JSON body `{"image":"data:image/jpeg;base64,..."}`
- `POST /api/reconstruct`：JSON body 包含图像和整数边界框 `{"image":"...","bbox":[x,y,width,height]}`
- `GET /api/models`
- `GET /api/settings` 与 `POST /api/settings`

设置接口当前仅接受请求，并**不会持久化设置**。不要将返回的默认设置视为已保存配置。

## 隐私与网络

图像帧会发送到配置的后端地址处理。默认后端为本机回环地址；不要把服务绑定到公网或把不可信地址作为 API 地址。浏览器会从 jsDelivr 加载 Three.js 模块；如需完全离线运行，需将该依赖下载并固定到项目内，再更新导入路径。

## 目前未验收 / 后续工作

- 真实浏览器端到端流程（摄像头 → 检测 → 重建 → WebGL 预览）。
- 多类物体检测的准确率、跨视频稳定性和性能基准。
- 更稳健的噪声/自交轮廓处理。
- 真正的多视角摄影测量重建（COLMAP SfM/MVS）；视频输入初检目前只做启发式质量评估，并不输出三维模型。
- GLB/GLTF 导出、设置持久化和设备兼容性测试。
