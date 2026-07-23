# PhotoCatch - AR物体识别与3D交互系统

一个完整的、完全免费的AR系统，可以识别视频中的物体、提取为3D模型，并在AR环境中交互。

## 🎯 功能特点

- ✅ **实时物体检测**：识别视频中的各类物体
- ✅ **3D模型提取**：自动生成物体的3D模型
- ✅ **AR交互**：在现实环境中展示和交互3D物体
- ✅ **完全免费**：无需付费API或第三方工具
- ✅ **开箱即用**：无复杂配置

## 📋 系统要求

- Python 3.8+
- 现代浏览器（Chrome、Firefox、Safari）
- 网络摄像头

## 🚀 快速开始

### 1. 安装依赖

```bash
git clone https://github.com/raymeigeni-dev/PhotoCatch.git
cd PhotoCatch

# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装Python依赖
pip install -r requirements.txt
```

### 2. 启动后端服务

```bash
python backend/server.py
```

服务器将在 `http://localhost:5000` 运行

### 3. 打开前端

在浏览器中打开 `frontend/index.html` 或使用HTTP服务器：

```bash
python -m http.server 8000
# 访问 http://localhost:8000/frontend/index.html
```

## 📖 使用说明

### 基本流程

1. **启动摄像头** - 点击"启动摄像头"按钮
2. **检测物体** - 点击"检测物体"（自动识别视频中的所有物体）
3. **选择物体** - 从列表中选择要提取的物体
4. **生成3D** - 点击"生成3D模型"
5. **AR交互** - 在右侧面板进行交互：
   - 🖱️ 拖动鼠标旋转
   - 🖱️ Shift+拖动平移
   - 🔍 滚轮缩放
   - ⚡ 点击"自动旋转"启用动画

### 高级功能

- **截图** - 保存当前摄像头画面
- **导出模型** - 以JSON格式导出3D模型数据
- **调整灵敏度** - 使用滑块调整物体检测灵敏度
- **模型质量** - 选择低/中/高质量（影响处理速度）

## 🎮 交互快捷键

| 操作 | 快捷键 |
|------|--------|
| 旋转 | 拖动鼠标 |
| 平移 | Shift + 拖动鼠标 |
| 缩放 | 鼠标滚轮 |
| 自动旋转 | 点击按钮 |
| 重置视图 | 点击"重置视图"按钮 |

## 🛠️ 项目结构

```
PhotoCatch/
├── README.md                 # 项目文档
├── requirements.txt          # Python依赖
├── backend/
│   ├── server.py            # Flask服务器
│   ├── detector.py          # 物体检测模块（MediaPipe）
│   ├── reconstructor.py     # 3D重建模块
│   └── utils.py             # 工具函数
├── frontend/
│   ├── index.html           # 主页面
│   ├── css/
│   │   └── style.css        # 样式表
│   └── js/
│       ├── main.js          # 主逻辑
│       ├── camera.js        # 摄像头控制
│       ├── detector.js      # 检测控制
│       ├── three-setup.js   # Three.js配置
│       └── ar.js            # AR渲染
└── models/                   # 预训练模型存储
```

## 🔧 技术栈

### 后端
- **Python 3.8+**
- **Flask 2.3+** - Web框架
- **OpenCV 4.8+** - 图像处理
- **MediaPipe 0.8+** - 物体检测
- **NumPy** - 数值计算
- **SciPy** - 科学计算

### 前端
- **HTML5** - 页面结构
- **CSS3** - 样式设计
- **JavaScript (ES6+)** - 交互逻辑
- **Three.js** - 3D渲染
- **WebGL** - GPU加速

## 💡 工作原理

### 1. 物体检测流程
```
视频帧 → OpenCV预处理 → MediaPipe检测 → 边界框标注 → 返回结果
```

### 2. 3D重建流程
```
ROI提取 → 边缘检测 → 轮廓提取 → 网格生成 → 颜色采样 → 3D模型
```

### 3. AR渲染流程
```
3D数据 → Three.js导入 → 灯光设置 → WebGL渲染 → 交互控制
```

## 🎨 支持的物体类型

系统可以检测以下类型的物体：

- 👤 人体和身体部位
- ✋ 手部和手势
- 😊 面部表情
- 📦 通用物体
- 🎨 自定义物体

## ⚙️ 性能参数

| 指标 | 性能 |
|------|------|
| 检测FPS | 15-30 |
| 3D重建时间 | 200-500ms |
| 模型顶点数 | 100-10000 |
| 模型面数 | 200-20000 |

## 🔐 隐私和安全

- ✅ 所有处理都在本地进行
- ✅ 不上传任何数据到云端
- ✅ 不需要互联网连接（摄像头访问除外）
- ✅ 完全开源，代码公开可审查

## 📝 许可证

MIT License - 自由使用、修改和分发

## 🤝 贡献指南

欢迎提交Issue和Pull Request！

### 报告Bug
1. 在GitHub中创建Issue
2. 描述问题和复现步骤
3. 提供系统信息

### 提交改进
1. Fork项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

## 🐛 故障排除

### 摄像头无法打开
```bash
# 检查摄像头权限
# macOS: 系统偏好设置 > 安全与隐私 > 摄像头
# Windows: 检查隐私设置 > 摄像头
# Linux: 检查 /dev/video* 权限
```

### 后端无响应
```bash
# 检查端口5000是否被占用
lsof -i :5000  # macOS/Linux
netstat -ano | findstr :5000  # Windows

# 使用不同的端口
python backend/server.py --port 5001
```

### 3D模型不显示
- 打开浏览器开发者工具 (F12)
- 检查控制台是否有错误
- 清除浏览器缓存
- 确保WebGL支持启用

## 🚀 未来计划

- [ ] 支持多物体同时提取
- [ ] 导出为GLTF/GLB格式
- [ ] AR眼镜设备支持
- [ ] 实时纹理映射
- [ ] 深度学习模型优化
- [ ] 物理引擎集成
- [ ] 云端同步功能

## 📞 支持

- 📚 查看README获取详细文档
- 💬 在GitHub Discussions中讨论
- 🐛 在Issues中报告问题

## 🙏 致谢

感谢以下开源项目的支持：
- MediaPipe
- OpenCV
- Three.js
- Flask

---

**祝你使用愉快！如有问题，欢迎反馈！** 🎉
