function renderModel(modelData) {
    if (!scene || !modelData || !Array.isArray(modelData.vertices) || !Array.isArray(modelData.faces)) {
        return;
    }

    if (mesh) {
        scene.remove(mesh);
        mesh.geometry?.dispose();
        if (Array.isArray(mesh.material)) {
            mesh.material.forEach((material) => material.dispose());
        } else {
            mesh.material?.dispose();
        }
    }

    let geometry;
    let wireframeGeometry;
    try {
        const indexedGeometry = new THREE.BufferGeometry();
        indexedGeometry.setAttribute(
            "position",
            new THREE.Float32BufferAttribute(modelData.vertices.flat(), 3)
        );
        indexedGeometry.setIndex(modelData.faces.flat());
        indexedGeometry.computeVertexNormals();

        // Backend colors are per face, but Three.js vertex color attributes are
        // per vertex. Expand indexed triangles so each face can retain one color.
        geometry = indexedGeometry.toNonIndexed();
        indexedGeometry.dispose();

        const material = new THREE.MeshPhongMaterial({
            color: 0xffffff,
            specular: 0x111111,
            shininess: 100,
            side: THREE.DoubleSide,
            wireframe: false,
            vertexColors: false
        });

        if (Array.isArray(modelData.colors) &&
            modelData.colors.length === modelData.faces.length &&
            modelData.colors.every((color) => Array.isArray(color) && color.length >= 3)) {
            const colors = [];
            for (const color of modelData.colors) {
                const rgb = color.slice(0, 3).map((channel) =>
                    Number.isFinite(channel) ? Math.max(0, Math.min(1, channel)) : 0.5
                );
                // Non-indexed geometry has exactly three vertices per triangle.
                colors.push(...rgb, ...rgb, ...rgb);
            }
            if (colors.length === geometry.getAttribute("position").count * 3) {
                geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
                material.vertexColors = true;
            }
        }

        geometry.computeVertexNormals();
        mesh = new THREE.Mesh(geometry, material);

        wireframeGeometry = new THREE.EdgesGeometry(geometry);
        const wireframe = new THREE.LineSegments(
            wireframeGeometry,
            new THREE.LineBasicMaterial({ color: 0x667eea })
        );
        mesh.add(wireframe);

        scene.add(mesh);
        adjustCameraToModel();
        Logger.info("3D模型已渲染");
    } catch (error) {
        geometry?.dispose();
        wireframeGeometry?.dispose();
        Logger.error(`渲染模型失败: ${error.message}`);
    }
}

function adjustCameraToModel() {
    if (!mesh || !camera) return;

    const box = new THREE.Box3().setFromObject(mesh);
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    if (!Number.isFinite(maxDim) || maxDim <= 0) return;

    const fov = camera.fov * (Math.PI / 180);
    let cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2));
    cameraZ *= 1.2;
    camera.position.z = cameraZ;
    camera.lookAt(mesh.position);
}
