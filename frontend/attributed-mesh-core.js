/**
 * Attribute-aware mesh model for PhotoCatch.
 *
 * Domains:
 *   vertex: one value per geometric vertex (color, skin weights, custom data)
 *   face: one value per polygon (materialIndex and face custom data)
 *   corner: one value per face corner (UV sets, split normals, tangents)
 *   edge: keyed by canonical geometric vertex pair (crease/sharp/custom edge data)
 *
 * Corner values deliberately remain attached to face corners when geometric
 * vertices are merged, so UV seams and split normals are not welded away.
 */
const cloneValue = value => {
  if (Array.isArray(value)) return value.map(cloneValue);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k,v]) => [k, cloneValue(v)]));
  return value;
};
const edgeKey = (a,b) => a < b ? `${a},${b}` : `${b},${a}`;
const finiteVec3 = v => Array.isArray(v) && v.length === 3 && v.every(Number.isFinite);

export function createAttributedMesh(input = {}) {
  const mesh = {
    vertices: (input.vertices || []).map(v => [...v]),
    faces: (input.faces || []).map(f => [...f]),
    attributes: {
      vertex: cloneValue(input.attributes?.vertex || {}),
      face: cloneValue(input.attributes?.face || {}),
      corner: cloneValue(input.attributes?.corner || {}),
      edge: cloneValue(input.attributes?.edge || {}),
      custom: cloneValue(input.attributes?.custom || {})
    },
    materialSlots: [...(input.materialSlots || [])],
    object: cloneValue(input.object || {name: 'Mesh', parent: null, transform: {location:[0,0,0], rotation:[0,0,0], scale:[1,1,1]}})
  };
  validateAttributedMesh(mesh);
  return mesh;
}

export function validateAttributedMesh(mesh) {
  if (!mesh || !Array.isArray(mesh.vertices) || !Array.isArray(mesh.faces) || !mesh.attributes)
    throw new TypeError('Attributed mesh requires vertices, faces and attribute domains');
  if (!mesh.vertices.every(finiteVec3)) throw new TypeError('Vertices must be finite 3D coordinates');
  for (const f of mesh.faces) {
    if (!Array.isArray(f) || f.length < 3 || f.some(i => !Number.isInteger(i) || i < 0 || i >= mesh.vertices.length) || new Set(f).size < 3)
      throw new TypeError('Invalid face indices');
  }
  for (const domain of ['vertex','face','corner','edge','custom']) {
    if (!mesh.attributes[domain] || typeof mesh.attributes[domain] !== 'object') throw new TypeError(`Missing ${domain} attribute domain`);
  }
  for (const [name, values] of Object.entries(mesh.attributes.vertex)) {
    if (!Array.isArray(values) || values.length !== mesh.vertices.length) throw new TypeError(`Vertex attribute ${name} length mismatch`);
  }
  for (const [name, values] of Object.entries(mesh.attributes.face)) {
    if (!Array.isArray(values) || values.length !== mesh.faces.length) throw new TypeError(`Face attribute ${name} length mismatch`);
  }
  for (const [name, perFace] of Object.entries(mesh.attributes.corner)) {
    if (!Array.isArray(perFace) || perFace.length !== mesh.faces.length || perFace.some((v,i) => !Array.isArray(v) || v.length !== mesh.faces[i].length))
      throw new TypeError(`Corner attribute ${name} must contain one value per face corner`);
  }
  return true;
}

export function cloneAttributedMesh(mesh) {
  return createAttributedMesh(mesh);
}

export function attributeAudit(mesh) {
  validateAttributedMesh(mesh);
  const domains = {};
  for (const domain of ['vertex','face','corner','edge','custom']) {
    domains[domain] = Object.entries(mesh.attributes[domain]).map(([name, values]) => ({
      name, count: Array.isArray(values) ? values.length : Object.keys(values || {}).length
    }));
  }
  return { domains, materialSlots: [...mesh.materialSlots], faceMaterialIndices: [...(mesh.attributes.face.materialIndex || [])] };
}

/** Move changes positions only; all other domains are byte-for-byte equivalent values. */
export function moveAttributedVertices(mesh, ids, delta) {
  validateAttributedMesh(mesh);
  for (const id of ids) if (mesh.vertices[id]) mesh.vertices[id] = mesh.vertices[id].map((x,k) => x + (Number(delta[k]) || 0));
  return { mesh, attributeReport: { preserved: Object.keys(mesh.attributes.vertex).concat(Object.keys(mesh.attributes.face),Object.keys(mesh.attributes.corner)), interpolated: [], inherited: [], regenerated: [], dropped: [], unsupported: [] } };
}

/**
 * Merge coincident/nearby positions while retaining each face's corner payload.
 * Conflicting vertex-domain values do not silently pick a winner: such vertices
 * stay distinct unless options.vertexAttributePolicy is 'first' or 'average'.
 */
export function mergeAttributedVertices(mesh, tolerance = 1e-5, options = {}) {
  validateAttributedMesh(mesh);
  const oldVertices = mesh.vertices.map(v => [...v]), oldFaces = mesh.faces.map(f => [...f]);
  const vertexAttrs = mesh.attributes.vertex, keys = Object.keys(vertexAttrs);
  const bins = new Map(), map = [], vertices = [], groups = [];
  const quant = Math.max(Math.abs(tolerance), 1e-12);
  for (let i=0;i<oldVertices.length;i++) {
    const v=oldVertices[i], key=v.map(x=>Math.round(x/quant)).join(',');
    let candidates=bins.get(key); if (!candidates) bins.set(key,candidates=[]);
    let id = candidates.find(candidate => {
      if (Math.hypot(...v.map((x,k)=>x-vertices[candidate][k])) > quant) return false;
      if (options.vertexAttributePolicy === 'first' || options.vertexAttributePolicy === 'average') return true;
      return keys.every(name => JSON.stringify(vertexAttrs[name][i]) === JSON.stringify(vertexAttrs[name][groups[candidate][0]]));
    });
    if (id === undefined) { id=vertices.length; vertices.push([...v]); groups.push([]); candidates.push(id); }
    groups[id].push(i); map[i]=id;
  }
  const faces = oldFaces.map(f => f.map(i=>map[i]));
  const keptFaces=[], keptIndices=[];
  faces.forEach((f,i) => { if (new Set(f).size >= 3) {keptFaces.push(f);keptIndices.push(i);} });
  const removedFaces = oldFaces.map((_,i)=>i).filter(i=>!keptIndices.includes(i));
  mesh.vertices=vertices; mesh.faces=keptFaces;
  for (const name of keys) mesh.attributes.vertex[name] = groups.map(group => {
    const values=group.map(i=>vertexAttrs[name][i]);
    if (options.vertexAttributePolicy === 'average' && values.every(v=>typeof v==='number')) return values.reduce((a,b)=>a+b,0)/values.length;
    return cloneValue(values[0]);
  });
  for (const domain of ['face']) for (const [name, values] of Object.entries(mesh.attributes[domain])) mesh.attributes[domain][name]=keptIndices.map(i=>values[i]);
  for (const [name, values] of Object.entries(mesh.attributes.corner)) mesh.attributes.corner[name]=keptIndices.map(i=>values[i]);
  const unsupported = Object.entries(mesh.attributes.custom).filter(([,v])=>v?.domain && !['vertex','face','corner','edge','object'].includes(v.domain)).map(([name])=>name);
  return {mesh, map, removedFaces, attributeReport:{
    preserved:Object.keys(mesh.attributes.corner).concat(Object.keys(mesh.attributes.face)),
    interpolated: options.vertexAttributePolicy==='average' ? keys : [],
    inherited: options.vertexAttributePolicy==='average' ? [] : keys,
    regenerated:[], dropped:[], unsupported
  }};
}

/** Delete polygons and all parallel face/corner values by identical face index. */
export function deleteAttributedFaces(mesh, faceIds) {
  validateAttributedMesh(mesh);
  const remove=new Set(faceIds), keep=mesh.faces.map((_,i)=>i).filter(i=>!remove.has(i));
  mesh.faces=keep.map(i=>mesh.faces[i]);
  for (const [name,values] of Object.entries(mesh.attributes.face)) mesh.attributes.face[name]=keep.map(i=>values[i]);
  for (const [name,values] of Object.entries(mesh.attributes.corner)) mesh.attributes.corner[name]=keep.map(i=>values[i]);
  return {mesh, attributeReport:{preserved:Object.keys(mesh.attributes.vertex).concat(Object.keys(mesh.attributes.face),Object.keys(mesh.attributes.corner)),interpolated:[],inherited:[],regenerated:[],dropped:[],unsupported:[]}};
}

/**
 * Extrude selected faces along a supplied normal. Caps inherit source face
 * material/face attributes and corner data; side faces inherit the material
 * index from their source face. Corner values for new side corners are copied
 * from the nearest source endpoint. Other face/corner attributes are reported.
 */
export function extrudeAttributedFaces(mesh, faceIds, distance=0.1, normal=[0,0,1]) {
  validateAttributedMesh(mesh);
  const chosen=[...new Set(faceIds)].filter(i=>Number.isInteger(i)&&i>=0&&i<mesh.faces.length);
  if (!chosen.length) return {mesh,attributeReport:{preserved:[],interpolated:[],inherited:[],regenerated:[],dropped:[],unsupported:[]}};
  const selected=new Set(chosen), oldFaces=mesh.faces.map(f=>[...f]), oldCount=mesh.faces.length;
  const oldFaceAttrs=cloneValue(mesh.attributes.face), oldCornerAttrs=cloneValue(mesh.attributes.corner);
  const oldEdgeFaces=new Map();
  oldFaces.forEach((f,fi)=>f.forEach((a,i)=>{const b=f[(i+1)%f.length],k=edgeKey(a,b);if(!oldEdgeFaces.has(k))oldEdgeFaces.set(k,[]);oldEdgeFaces.get(k).push(fi)}));
  const boundary=[];
  for (const fi of chosen) { const f=oldFaces[fi]; for(let i=0;i<f.length;i++){const a=f[i],b=f[(i+1)%f.length],incident=oldEdgeFaces.get(edgeKey(a,b))||[];if(incident.length===1||!incident.every(j=>selected.has(j))) boundary.push({a,b,source:fi});}}
  const uniqueBoundary=[...new Map(boundary.map(e=>[edgeKey(e.a,e.b),e])).values()];
  const used=[...new Set(chosen.flatMap(i=>oldFaces[i]))], newId=new Map();
  const n=normal.map(Number), nl=Math.hypot(...n)||1;
  for(const id of used){newId.set(id,mesh.vertices.length);mesh.vertices.push(mesh.vertices[id].map((x,k)=>x+n[k]/nl*distance));}
  for(const [name,values] of Object.entries(mesh.attributes.vertex)) {
    const extra=used.map(id=>cloneValue(values[id])); mesh.attributes.vertex[name]=[...values,...extra];
  }
  const faceSource=oldFaces.map((_,i)=>i).filter(i=>!selected.has(i));
  mesh.faces=faceSource.map(i=>oldFaces[i]);
  for(const [name,values] of Object.entries(mesh.attributes.face)) mesh.attributes.face[name]=faceSource.map(i=>cloneValue(oldFaceAttrs[name][i]));
  for(const [name,values] of Object.entries(mesh.attributes.corner)) mesh.attributes.corner[name]=faceSource.map(i=>cloneValue(oldCornerAttrs[name][i]));
  for(const fi of chosen) {
    mesh.faces.push(oldFaces[fi].map(id=>newId.get(id)));
    for(const [name,values] of Object.entries(mesh.attributes.face)) values.push(cloneValue(oldFaceAttrs[name][fi]));
    for(const [name,values] of Object.entries(mesh.attributes.corner)) values.push(cloneValue(oldCornerAttrs[name][fi]));
  }
  for(const e of uniqueBoundary) {
    const f=[e.a,e.b,newId.get(e.b),newId.get(e.a)], src=e.source;
    mesh.faces.push(f);
    for(const [name,values] of Object.entries(mesh.attributes.face)) values.push(cloneValue(oldFaceAttrs[name][src]));
    for(const [name,values] of Object.entries(mesh.attributes.corner)) {
      const original=oldCornerAttrs[name][src], face=oldFaces[src], ia=face.indexOf(e.a), ib=face.indexOf(e.b);
      const va=cloneValue(original[ia]), vb=cloneValue(original[ib]);
      values.push([va,vb,cloneValue(vb),cloneValue(va)]);
    }
  }
  return {mesh,attributeReport:{preserved:Object.keys(mesh.attributes.vertex).concat(Object.keys(mesh.attributes.face),Object.keys(mesh.attributes.corner)),interpolated:[],inherited:Object.keys(mesh.attributes.face).concat(Object.keys(mesh.attributes.corner)),regenerated:[],dropped:[],unsupported:Object.keys(mesh.attributes.custom)}};
}

/**
 * Rebuild one face. Caller supplies vertex ids and optional barycentric/source
 * corner indices. Material index and face attributes inherit from sourceFace;
 * corner attributes require explicit sourceCorners or are rejected.
 */
export function rebuildAttributedFace(mesh, vertices, {sourceFace, sourceCorners}={}) {
  validateAttributedMesh(mesh);
  if (!Number.isInteger(sourceFace) || sourceFace<0 || sourceFace>=mesh.faces.length) throw new TypeError('sourceFace is required to inherit face attributes safely');
  if (!Array.isArray(sourceCorners) || sourceCorners.length!==vertices.length) throw new TypeError('sourceCorners mapping is required; corner attributes cannot be guessed safely');
  if (vertices.length<3 || vertices.some(i=>!Number.isInteger(i)||i<0||i>=mesh.vertices.length) || new Set(vertices).size<3) throw new TypeError('Rebuilt face indices are invalid');
  mesh.faces.push([...vertices]);
  for (const [name,values] of Object.entries(mesh.attributes.face)) values.push(cloneValue(values[sourceFace]));
  for (const [name,values] of Object.entries(mesh.attributes.corner)) {
    const source=values[sourceFace];
    mesh.attributes.corner[name].push(sourceCorners.map(i=>{
      if (!Number.isInteger(i)||i<0||i>=source.length) throw new TypeError(`Invalid source corner mapping for ${name}`);
      return cloneValue(source[i]);
    }));
  }
  return {mesh,attributeReport:{preserved:[],interpolated:[],inherited:Object.keys(mesh.attributes.face),regenerated:[],dropped:[],unsupported:Object.keys(mesh.attributes.custom)}};
}
