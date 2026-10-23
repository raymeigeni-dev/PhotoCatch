import { moveAttributedVertices, mergeAttributedVertices, deleteAttributedFaces, extrudeAttributedFaces, rebuildAttributedFace } from './attributed-mesh-core.js';
/**
 * PhotoCatch mesh editing core.
 * Pure data operations; vertices are [x,y,z], faces are arrays of vertex indices.
 * Non-indexed triangle soup is supported through fromTriangleSoup().
 */
const EPS = 1e-10;
const vec = (a,b)=>[a[0]-b[0],a[1]-b[1],a[2]-b[2]];
const cross = (a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const dot = (a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
const length = a=>Math.sqrt(dot(a,a));
const norm = a=>{const n=length(a);return n>EPS?a.map(x=>x/n):[0,0,0]};
const keyEdge=(a,b)=>a<b?a+','+b:b+','+a;
const keyFace=f=>f.slice().sort((a,b)=>a-b).join(',');
const clone=m=>({vertices:m.vertices.map(v=>v.slice()),faces:m.faces.map(f=>f.slice())});

export function createMesh(vertices=[], faces=[]) {
  const mesh={vertices:vertices.map(v=>v.map(Number)),faces:faces.map(f=>f.map(Number))};
  validateMesh(mesh); return mesh;
}
export function validateMesh(mesh) {
  if(!mesh || !Array.isArray(mesh.vertices)||!Array.isArray(mesh.faces)) throw new TypeError('Mesh must contain vertices and faces arrays');
  for(const v of mesh.vertices) if(!Array.isArray(v)||v.length!==3||!v.every(Number.isFinite)) throw new TypeError('Each vertex must be three finite coordinates');
  for(const f of mesh.faces) if(!Array.isArray(f)||f.length<3||f.some(i=>!Number.isInteger(i)||i<0||i>=mesh.vertices.length)||new Set(f).size<3) throw new TypeError('Face has invalid vertex indices');
  return true;
}
export function fromIndexedGeometry(positions, indices) {
  const vertices=[]; for(let i=0;i<positions.length;i+=3) vertices.push([+positions[i],+positions[i+1],+positions[i+2]]);
  const ids=indices?Array.from(indices):vertices.map((_,i)=>i), faces=[];
  for(let i=0;i+2<ids.length;i+=3) faces.push([ids[i],ids[i+1],ids[i+2]]);
  return createMesh(vertices,faces);
}
export function fromTriangleSoup(positions) {
  const vertices=[]; for(let i=0;i+8<positions.length;i+=9) vertices.push([+positions[i],+positions[i+1],+positions[i+2]],[+positions[i+3],+positions[i+4],+positions[i+5]],[+positions[i+6],+positions[i+7],+positions[i+8]]);
  return createMesh(vertices,vertices.reduce((a,_,i)=>{if(i%3===0)a.push([i,i+1,i+2]);return a},[]));
}
export function toTriangleSoup(mesh) {
  validateMesh(mesh); const out=[];
  for(const f of mesh.faces) for(let i=1;i<f.length-1;i++) for(const id of [f[0],f[i],f[i+1]]) out.push(...mesh.vertices[id]);
  return new Float32Array(out);
}
export function buildTopology(mesh) {
  validateMesh(mesh); const edges=new Map(), vertexFaces=mesh.vertices.map(()=>[]), vertexNeighbors=mesh.vertices.map(()=>new Set());
  mesh.faces.forEach((face,fi)=>{face.forEach((v,i)=>{vertexFaces[v].push(fi);const w=face[(i+1)%face.length];vertexNeighbors[v].add(w);vertexNeighbors[w].add(v);const k=keyEdge(v,w);if(!edges.has(k))edges.set(k,{vertices:[Math.min(v,w),Math.max(v,w)],faces:[]});edges.get(k).faces.push(fi)})});
  const boundary=[],manifold=[],nonManifold=[];
  for(const e of edges.values()){if(e.faces.length===1)boundary.push(e);else if(e.faces.length===2)manifold.push(e);else nonManifold.push(e)}
  return {edges:[...edges.values()],edgeMap:edges,vertexFaces,vertexNeighbors:vertexNeighbors.map(s=>[...s]),boundaryEdges:boundary,manifoldEdges:manifold,nonManifoldEdges:nonManifold};
}
export function selectByVertexIds(mesh, ids) { const valid=new Set(ids.filter(i=>Number.isInteger(i)&&i>=0&&i<mesh.vertices.length));return {vertices:[...valid],edges:buildTopology(mesh).edges.filter(e=>valid.has(e.vertices[0])&&valid.has(e.vertices[1])).map(e=>e.vertices),faces:mesh.faces.map((f,i)=>f.every(v=>valid.has(v))?i:-1).filter(i=>i>=0)}; }
export function selectByFaceIds(mesh, ids) { const topo=buildTopology(mesh), faces=[...new Set(ids)].filter(i=>Number.isInteger(i)&&i>=0&&i<mesh.faces.length), vertices=new Set(faces.flatMap(i=>mesh.faces[i]));return {faces,vertices:[...vertices],edges:topo.edges.filter(e=>e.faces.some(i=>faces.includes(i))).map(e=>e.vertices)}; }
export function selectScreenRegion(projected, region) {
  const inside=(p,pts)=>{let yes=false;for(let i=0,j=pts.length-1;i<pts.length;j=i++){const a=pts[i],b=pts[j];if(((a.y>p.y)!==(b.y>p.y))&&p.x<(b.x-a.x)*(p.y-a.y)/(b.y-a.y)+a.x)yes=!yes}return yes};
  return projected.filter(p=>{if(p.z < -1||p.z>1)return false;if(region.kind==='box')return p.x>=region.minX&&p.x<=region.maxX&&p.y>=region.minY&&p.y<=region.maxY;if(region.kind==='brush')return Math.hypot(p.x-region.x,p.y-region.y)<=region.radius;return (region.kind==='lasso'||region.kind==='polygon')&&region.points.length>=3&&inside(p,region.points)}).map(p=>p.index);
}
export function moveVertices(mesh, ids, delta) {
  validateMesh(mesh);
  if (mesh.attributes) { const result=moveAttributedVertices(mesh,ids,delta); mesh.lastAttributeReport=result.attributeReport; return mesh; }
  for(const i of ids){if(!mesh.vertices[i])continue;mesh.vertices[i]=mesh.vertices[i].map((v,k)=>v+(+delta[k]||0))}
  return mesh;
}
export function mergeVertices(mesh, tolerance=1e-5, options={}) {
  validateMesh(mesh);
  if (mesh.attributes) { const result=mergeAttributedVertices(mesh,tolerance,options); mesh.lastAttributeReport=result.attributeReport; mesh.lastVertexMergeMap=result.map; mesh.lastRemovedFaces=result.removedFaces; return mesh; }
  const out=[],map=[],bins=new Map();
  for(const v of mesh.vertices){const k=v.map(x=>Math.round(x/Math.max(tolerance,EPS))).join(',');let id=bins.get(k);if(id===undefined){id=out.length;out.push(v.slice());bins.set(k,id)}map.push(id)}
  const faces=[];for(const f of mesh.faces){const nf=f.map(i=>map[i]).filter((v,i,a)=>i===0||v!==a[i-1]);if(nf.length>2&&nf[0]===nf[nf.length-1])nf.pop();if(new Set(nf).size>=3)faces.push(nf)}
  mesh.vertices=out;mesh.faces=faces;return mesh;
}
export function deleteFaces(mesh, ids) {
  if (mesh?.attributes) { const result=deleteAttributedFaces(mesh,ids); mesh.lastAttributeReport=result.attributeReport; return mesh; }
  const remove=new Set(ids);mesh.faces=mesh.faces.filter((_,i)=>!remove.has(i));return mesh;
}
export function extrudeFaces(mesh, ids, distance=0.1) {
  validateMesh(mesh);
  if (mesh.attributes) { const result=extrudeAttributedFaces(mesh,ids,distance); mesh.lastAttributeReport=result.attributeReport; return mesh; }
  const chosen=[...new Set(ids)].filter(i=>i>=0&&i<mesh.faces.length);if(!chosen.length)return mesh;
  const topo=buildTopology(mesh),selected=new Set(chosen),boundary=new Map();
  for(const fi of chosen){const f=mesh.faces[fi];for(let i=0;i<f.length;i++){const a=f[i],b=f[(i+1)%f.length],e=topo.edgeMap.get(keyEdge(a,b));if(e.faces.length===1||!e.faces.every(x=>selected.has(x))){const k=keyEdge(a,b);if(!boundary.has(k))boundary.set(k,{a,b})}}}
  const normals=mesh.vertices.map(()=>[0,0,0]);
  for(const f of mesh.faces){const n=cross(vec(mesh.vertices[f[1]],mesh.vertices[f[0]]),vec(mesh.vertices[f[2]],mesh.vertices[f[0]]));for(const id of f)normals[id]=normals[id].map((x,k)=>x+n[k])}
  const newIds=new Map();for(const fi of chosen)for(const id of mesh.faces[fi])if(!newIds.has(id)){const n=norm(normals[id]);newIds.set(id,mesh.vertices.length);mesh.vertices.push(mesh.vertices[id].map((x,k)=>x+n[k]*distance))}
  const oldFaces=mesh.faces.filter((_,i)=>!selected.has(i));const caps=chosen.map(fi=>mesh.faces[fi].map(id=>newIds.get(id)));
  const sides=[];for(const {a,b} of boundary.values()){const A=newIds.get(a),B=newIds.get(b);sides.push([a,b,B],[a,B,A])}
  mesh.faces=[...oldFaces,...caps,...sides];return mesh;
}
/** Rebuild a face on an attributed mesh using explicit source-corner mapping. */
export function rebuildFace(mesh, vertices, options={}) {
  if (!mesh?.attributes) throw new TypeError('rebuildFace requires an attributed mesh');
  const result=rebuildAttributedFace(mesh,vertices,options);
  mesh.lastAttributeReport=result.attributeReport;
  return mesh;
}
export function sculpt(mesh, center, radius, strength, mode='push', selectedIds=null) {
  validateMesh(mesh);if(radius<=0)return mesh;const allow=selectedIds?new Set(selectedIds):null;
  const normals=mesh.vertices.map(()=>[0,0,0]);for(const f of mesh.faces){const n=cross(vec(mesh.vertices[f[1]],mesh.vertices[f[0]]),vec(mesh.vertices[f[2]],mesh.vertices[f[0]]));for(const id of f)normals[id]=normals[id].map((x,k)=>x+n[k])}
  for(let i=0;i<mesh.vertices.length;i++){if(allow&&!allow.has(i))continue;const v=mesh.vertices[i],d=length(vec(v,center));if(d>radius)continue;const falloff=(1-(d/radius)**2)**2,sign=mode==='pull'?-1:1,n=norm(normals[i]);mesh.vertices[i]=v.map((x,k)=>x+n[k]*strength*falloff*sign)}return mesh;
}
export function inspectMesh(mesh, areaEpsilon=1e-10) {
  validateMesh(mesh);const topo=buildTopology(mesh),degenerate=[],duplicate=[],seen=new Map();
  mesh.faces.forEach((f,i)=>{const a=mesh.vertices[f[0]],b=mesh.vertices[f[1]],c=mesh.vertices[f[2]],area=length(cross(vec(b,a),vec(c,a)))*.5;if(area<=areaEpsilon||new Set(f).size<3)degenerate.push(i);const k=keyFace(f);if(seen.has(k))duplicate.push(i);else seen.set(k,i)});
  return {vertices:mesh.vertices.length,faces:mesh.faces.length,edges:topo.edges.length,boundaryEdges:topo.boundaryEdges.length,nonManifoldEdges:topo.nonManifoldEdges.map(e=>({vertices:e.vertices,faceCount:e.faces.length})),degenerateFaces:degenerate,duplicateFaces:duplicate,watertight:topo.boundaryEdges.length===0&&topo.nonManifoldEdges.length===0&&mesh.faces.length>0};
}
export function repairMesh(mesh, options={}) {
  validateMesh(mesh);const before=inspectMesh(mesh),epsilon=options.areaEpsilon??1e-10;
  let report={removedDegenerate:0,removedDuplicate:0,splitNonManifoldEdges:0};
  const seen=new Set(),faces=[];mesh.faces.forEach(f=>{const a=mesh.vertices[f[0]],b=mesh.vertices[f[1]],c=mesh.vertices[f[2]],area=length(cross(vec(b,a),vec(c,a)))*.5;if(area<=epsilon){report.removedDegenerate++;return}const k=keyFace(f);if(seen.has(k)){report.removedDuplicate++;return}seen.add(k);faces.push(f)});mesh.faces=faces;
  let topo=buildTopology(mesh);for(const edge of topo.nonManifoldEdges){const extra=edge.faces.slice(2);for(const fi of extra){const f=mesh.faces[fi];for(const old of edge.vertices){const id=mesh.vertices.length;mesh.vertices.push(mesh.vertices[old].slice());const at=f.indexOf(old);if(at>=0)f[at]=id}report.splitNonManifoldEdges++}}
  const used=new Set(mesh.faces.flat()),map=new Map(),vertices=[];for(const id of used){map.set(id,vertices.length);vertices.push(mesh.vertices[id])}mesh.vertices=vertices;mesh.faces=mesh.faces.map(f=>f.map(id=>map.get(id)));
  const after=inspectMesh(mesh);return {mesh,report,before,after};
}
export function cloneMesh(mesh) { return clone(mesh); }
