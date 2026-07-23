function renderModel(modelData) {
    if (!scene || !modelData) return;
    
    if (mesh) {
        scene.remove(mesh);
    }
    
    try {
        const geometry = new THREE.BufferGeometry();
        
        const vertices = new Float32Array(modelData.vertices.flat());
        geometry.setAttribute('position', new THREE.BufferAttribute(vertices, 3));
        
        const indices = new Uint32Array(modelData.faces.flat());
        geometry.setIndex(new THREE.BufferAttribute(indices, 1));
        
        geometry.computeVertexNormals();
        
        const material = new THREE.MeshPhongMaterial({
            color: 0x888888,
            specular: 0x111111,
            shininess: 100,
            side: THREE.DoubleSide,
            wireframe: false
        });
        
        if (modelData.colors && modelData.colors.length > 0) {
            const colors = [];
            for (let i = 0; i < modelData.colors.length; i++) {
                for (let j = 0; j < 3; j++) {
                    colors.push(...modelData.colors[i]);
                }
            }
            geometry.setAttribute('color', new THREE.BufferAttribute(new Float32Array(colors), 3));
            material.vertexColors = true;
        }
        
        mesh = new THREE.Mesh(geometry, material);
        
        const edges = new THREE.EdgesGeometry(geometry);
        const wireframe = new THREE.LineSegments(edges, new THREE.LineBasicMaterial({ color: 0x667eea }));
        mesh.add(wireframe);
        
        scene.add(mesh);
        adjustCameraToModel();
        
        Logger.info('3D模型已渲染');
    } catch (error) {
        Logger.error(`渲染模型失败: ${error.message}`);
    }
}

function adjustCameraToModel() {
    if (!mesh) return;
    
    const box = new THREE.Box3().setFromObject(mesh);
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    const fov = camera.fov * (Math.PI / 180);
    let cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2));
    
    cameraZ *= 1.2;
    camera.position.z = cameraZ;
    camera.lookAt(mesh.position);
}
