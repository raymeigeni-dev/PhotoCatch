# PhotoCatch — 实验性多视角 3D 重建与网格质量检查

PhotoCatch 是一个本地运行的实验性原型，包含两条不同能力的流程：摄像头单帧检测/二维轮廓挤出，以及从视频抽帧后尝试 COLMAP/OpenMVS 多视角摄影测量。两者不能混为一谈；单帧挤出不是实物扫描，多视角流程生成网格也不代表几何、颜色或纹理已完整还原。

> **能力边界：** 当前检测器基于 MediaPipe Hands、Pose 与 Selfie Segmentation，并非通用物体检测器。代码中的检测 confidence 数值目前是固定常量，不是经过校准的模型置信度，不能用于严肃的准确率判断。当前 3D 算法是单张图像的轮廓挤出，不是多视角摄影测量，也不会恢复真实背面、真实深度或可靠的物理尺寸。结果适用于原型验证，不应宣传为完整的真实物体 3D 扫描。


## 多引擎重建（本分支新增）

- `GET /api/reconstruction/engines`：查看 OpenMVS、Apple Object Capture 和云端网关的实际配置状态。
- OpenMVS 路线：在 Mac 上通过 `InterfaceCOLMAP`、`DensifyPointCloud`、`ReconstructMesh` 执行 CPU 稠密重建；若安装 `RefineMesh` 会尝试细化，若安装 `TextureMesh` 会尝试 UV 纹理烘焙。响应中的 `texturing.success` 才是是否发现纹理 OBJ 的信号；未成功时不能把 PLY 当作照片级彩色模型。
- Apple Object Capture：已有 `POST /api/video/reconstruct/apple` 视频接口，依赖编译好的原生 helper；必须在目标 Mac 上真实测试，代码存在不代表可用。
- 云端：`POST /api/video/reconstruct/cloud` 提交任务，`GET /api/video/reconstruct/cloud/<job_id>` 轮询，`GET /api/video/reconstruct/cloud/<job_id>/result` 读取结果清单。它是可配置的 HTTP 网关适配器，不是直接开箱即用的 RealityCapture 官方连接；需配置 `PHOTOCATCH_CLOUD_API_BASE_URL` 和 `PHOTOCATCH_CLOUD_API_TOKEN`。
- 云端资产清单目前不会自动下载到 Mac；云端任务成功也不代表模型质量已验收。

## 当前功能

- 本地 Flask API：健康检查、候选区域检测、ROI 网格生成。
- 普通视频（MP4/MOV 等）输入初检与真实多视图重建尝试。
- Insta360 / GoPro MAX 标准 2:1 等距柱状投影视频：可选择 360°模式，将每个采样帧投影为 6 个同内参的重叠透视视图，再送入 COLMAP SfM/MVS。
- 可选 COLMAP SfM/MVS 流程：特征提取、匹配、稀疏重建、深度估计、深度融合和 Poisson 网格生成；COLMAP 失败时明确返回错误，不回退成伪 3D。
- 网格质量门禁：检查有限顶点、有效三角面、重复面、退化面、包围盒、表面积、连通组件、水密性和纹理数据，并在 UI 中展示相机注册数量与质量警告。
- 摄像头捕获、候选区域选择和 API 错误提示。
- Three.js 交互式网格预览：拖动旋转、滚轮缩放。
- 导出当前网格为 JSON。
- 输入校验和后端自动化测试。
- GitHub Actions 自动运行 Python 测试。

## 环境要求

- Python 3.11（CI 使用版本；建议本地也使用 3.11）
- 可访问摄像头的现代浏览器
- 本地 Python 依赖安装需要网络；真正多视角重建需要 COLMAP 命令行程序，并确保 `colmap` 位于 PATH。COLMAP 的稠密 PatchMatch 立体重建要求 CUDA；在没有 CUDA 的 Mac 上，若安装了 OpenMVS 的 `InterfaceCOLMAP`、`DensifyPointCloud`、`ReconstructMesh` 并位于 PATH，PhotoCatch 会尝试切换到 OpenMVS CPU SGM 稠密重建。CPU 重建可能明显更慢，且仍需真实视频验收；网格质量检查使用 `trimesh`（已列入 requirements.txt）
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

导入视频后，先在“重建模式”中选择普通视频或 360°全景，再点击“提取多帧并评估”。360°模式要求设备官方软件导出的完整、接近 2:1 的等距柱状投影文件。初检通过时可点击“运行 COLMAP 多视角重建”；该过程要求已安装 COLMAP，可能消耗较多 CPU、内存和磁盘空间。COLMAP 的稠密 PatchMatch 若因缺少 CUDA 失败，会在检测到 OpenMVS 命令行工具时尝试 CPU SGM 备选流程；否则会明确报错并保留已完成的稀疏重建，不会伪造完整网格。摄像头单帧检测仍可用于原型试验，但它不是多视角重建。后端地址默认是 `http://127.0.0.1:5000`。如需指定其他 API 地址，可在 URL 中加入 `?api=http://127.0.0.1:5001`（仅限可信的本地服务）。

## Apple RealityKit Object Capture（新增实验性原生工具）

PhotoCatch 正在评估苹果官方 RealityKit Object Capture 作为额外重建后端。集成方案和验收标准见 [Apple Object Capture 集成计划](docs/apple-object-capture-integration-plan.md)。

原生 Swift 工具位于 `native/apple-object-capture/`，使用 macOS 的 `PhotogrammetrySession` 将一组多视角照片重建为 USDZ。它会先检查 `PhotogrammetrySession.isSupported`，并以 JSON 输出支持状态、输入图像数和输出文件大小。视频仍需先抽取清晰、角度有差异的图像；工具不会直接把 MOV 当作照片目录。

在装有 Xcode Command Line Tools 的受支持 Mac 上，从仓库根目录运行：

```bash
cd native/apple-object-capture
swift build -c release
swift run -c release photocatch-apple-capture /absolute/path/to/job/images /absolute/path/to/job/model.usdz
```

注意：这只是独立原生工具，尚未接入 Flask 视频重建 API，也未在目标 Mac 上实机编译或使用 `IMG_0096.MOV` 验收。不要将该工具的存在描述为苹果重建已在 PhotoCatch 中可用。iPhone LiDAR 的引导式采集是独立的后续 iOS 伴随应用工作，不等同于 Mac 端重建。

## 自动化测试

```bash
python -m pytest -q
```

测试覆盖工具函数、API 输入校验、网格拓扑不变量、凹多边形三角剖分，以及前端入口文件和关键控件的静态冒烟检查。静态前端测试**不等于**真实浏览器端到端测试；真实摄像头、WebGL 渲染与不同设备兼容性仍需实际运行验收。

## API

- `GET /api/health`
- `POST /api/video/analyze`：multipart/form-data，字段名 `video`，可选 `mode=ordinary|panorama360`；提取最多 24 帧并返回清晰度、亮度、几何一致性、视差启发式指标及预览帧。初检不是重建结果，也不能单独证明相机运动或 SfM 可解。
- `POST /api/video/reconstruct`：multipart/form-data，字段名 `video`，可选 `mode=ordinary|panorama360`；先执行输入初检，再调用本机 COLMAP SfM/MVS，成功时返回网格 URL。未通过输入门槛、未安装 COLMAP 或重建失败时会返回明确错误，不会伪造成功。
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
- 真实视频/真实物体的重建质量验收仍依赖实际运行 COLMAP/OpenMVS 的素材、计算环境和人工检查；输入初检指标只是启发式，不保证模型完整或可辨认。
- 360°全景路径已过滤同一源帧的虚拟视图匹配，但尚未向 COLMAP 注入已知的虚拟相机相对旋转/rig frame 约束；不能把它视为已完成的严谨全景摄影测量。
- OpenMVS CPU SGM 路径增加了 `scene.mvs`、`scene_dense.mvs`、`scene_dense.ply` 和网格输出检查，并将产物规范化为 API 使用的 `mesh.ply` / `fused.ply`；Mac 上是否可用仍取决于实际安装的 OpenMVS 构建和真实素材。
- 输出目前为 PLY 网格/点云；当前流程不生成真实 UV 纹理贴图，且输出未必包含顶点颜色，因此白色/单色模型是当前管线的能力限制，不是通过调整渲染颜色就能修复的问题。高保真外观需要新增纹理重建/贴图流程，并通过真实素材验证。网格检查可以报告水密性、连通组件和退化面，但不能自动判断目标身份或视觉逼真程度；真实素材、浏览器 E2E、孔洞/碎片人工验收和尺度恢复仍需后续完成。
- GLB/GLTF 导出、设置持久化和设备兼容性测试。
