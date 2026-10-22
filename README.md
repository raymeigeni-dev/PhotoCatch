# PhotoCatch — 摄像头检测与实验性 3D 网格预览

PhotoCatch 是一个本地运行的实验性原型：通过摄像头抓取单帧，调用本地 Flask 后端检测候选区域，再把选中区域的二维轮廓沿深度方向挤出为三角网格，并在浏览器中交互预览。

> **能力边界：** 当前检测器基于 MediaPipe Hands、Pose 与 Selfie Segmentation，并非通用物体检测器。代码中的检测 confidence 数值目前是固定常量，不是经过校准的模型置信度，不能用于严肃的准确率判断。当前 3D 算法是单张图像的轮廓挤出，不是多视角摄影测量，也不会恢复真实背面、真实深度或可靠的物理尺寸。结果适用于原型验证，不应宣传为完整的真实物体 3D 扫描。

## 当前功能

- 本地 Flask API：健康检查、候选区域检测、ROI 网格生成。
- 视频导入（MP4/MOV 等）、时间分布抽帧、清晰度/亮度/几何一致性/视差初检和代表帧预览。
- 可选 COLMAP SfM/MVS 流程：特征提取、匹配、稀疏重建、深度估计、深度融合和 Poisson 网格生成；COLMAP 失败时明确返回错误，不回退成伪 3D。
- 摄像头捕获、候选区域选择和 API 错误提示。
- Three.js 交互式网格预览：拖动旋转、滚轮缩放。
- 导出当前网格为 JSON。
- 输入校验和后端自动化测试。
- GitHub Actions 自动运行 Python 测试。

## 环境要求

- Python 3.11（CI 使用版本；建议本地也使用 3.11）
- 可访问摄像头的现代浏览器
- 本地 Python 依赖安装需要网络；真正多视角重建还需要单独安装 COLMAP 命令行程序，并确保 `colmap` 位于 PATH
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

导入视频后点击“提取多帧并评估”。初检通过时可点击“运行 COLMAP 多视角重建”；该过程要求已安装 COLMAP，可能消耗较多 CPU、内存和磁盘空间。摄像头单帧检测仍可用于原型试验，但它不是多视角重建。后端地址默认是 `http://127.0.0.1:5000`。如需指定其他 API 地址，可在 URL 中加入 `?api=http://127.0.0.1:5001`（仅限可信的本地服务）。

## 自动化测试

```bash
python -m pytest -q
```

测试覆盖工具函数、API 输入校验、网格拓扑不变量、凹多边形三角剖分，以及前端入口文件和关键控件的静态冒烟检查。静态前端测试**不等于**真实浏览器端到端测试；真实摄像头、WebGL 渲染与不同设备兼容性仍需实际运行验收。

## API

- `GET /api/health`
- `POST /api/video/analyze`：multipart/form-data，字段名 `video`；提取最多 24 帧并返回清晰度、亮度、几何一致性、视差启发式指标及预览帧。初检不是重建结果，也不能单独证明相机运动或 SfM 可解。
- `POST /api/video/reconstruct`：multipart/form-data，字段名 `video`；先执行保守初检，再调用本机 COLMAP SfM/MVS，成功时返回网格 URL。未通过输入门槛、未安装 COLMAP 或重建失败时会返回明确错误，不会伪造成功。
- `GET /api/video/models/{job_id}/mesh.ply` 与 `pointcloud.ply`：读取已生成的 PLY 资产。
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
- 真实视频/真实物体的重建质量验收仍依赖实际运行 COLMAP 的素材、计算环境和人工检查；输入初检指标只是启发式，不保证模型完整或可辨认。
- 输出目前为 PLY 网格/点云；真实纹理贴图、自动网格连通性/孔洞检查、尺度恢复和完整浏览器 E2E 测试仍需后续验收。
- GLB/GLTF 导出、设置持久化和设备兼容性测试。
