import test from 'node:test';
import assert from 'node:assert/strict';
import {createMesh,fromIndexedGeometry,fromTriangleSoup,buildTopology,selectByVertexIds,selectByFaceIds,selectScreenRegion,moveVertices,mergeVertices,extrudeFaces,sculpt,inspectMesh,repairMesh,toTriangleSoup} from '../frontend/mesh-editing-core.js';

test('indexed and non-indexed geometry normalize to valid topology',()=>{
 const indexed=fromIndexedGeometry([0,0,0,1,0,0,0,1,0],[0,1,2]);
 assert.equal(buildTopology(indexed).edges.length,3);
 const soup=fromTriangleSoup([0,0,0,1,0,0,0,1,0]);
 assert.equal(soup.vertices.length,3);assert.equal(soup.faces.length,1);assert.equal(toTriangleSoup(soup).length,9);
});
test('topology reports adjacency and boundary edges',()=>{
 const m=createMesh([[0,0,0],[1,0,0],[1,1,0],[0,1,0]],[[0,1,2],[0,2,3]]);
 const t=buildTopology(m);assert.equal(t.edges.length,5);assert.equal(t.boundaryEdges.length,4);assert.equal(t.edgeMap.get('0,2').faces.length,2);
});
test('multi-vertex and multi-face selections return connected elements',()=>{
 const m=createMesh([[0,0,0],[1,0,0],[1,1,0],[0,1,0]],[[0,1,2],[0,2,3]]);
 assert.deepEqual(selectByVertexIds(m,[0,2,999]).faces,[0,1]);
 assert.deepEqual(selectByFaceIds(m,[1]).vertices,[0,2,3]);
 assert.deepEqual(selectScreenRegion([{index:0,x:5,y:5,z:0},{index:1,x:30,y:30,z:0}],{kind:'box',minX:0,maxX:10,minY:0,maxY:10}),[0]);
 assert.deepEqual(selectScreenRegion([{index:0,x:5,y:5,z:0}],{kind:'lasso',points:[{x:0,y:0},{x:10,y:0},{x:10,y:10},{x:0,y:10}]}),[0]);
});
test('joint vertex move and merge preserve valid face indices',()=>{
 const m=createMesh([[0,0,0],[1,0,0],[0,1,0],[0,0,0]],[[0,1,2]]);
 mergeVertices(m,1e-5);moveVertices(m,[0,1],[0,0,1]);
 assert.equal(m.vertices.length,3);assert.deepEqual(m.vertices[0],[0,0,1]);assert.equal(inspectMesh(m).degenerateFaces.length,0);
});
test('face extrusion adds cap and side-wall topology',()=>{
 const m=createMesh([[0,0,0],[1,0,0],[0,1,0]],[[0,1,2]]);
 const before=inspectMesh(m);extrudeFaces(m,[0],1);const after=inspectMesh(m);
 assert.equal(m.vertices.length,6);assert.equal(m.faces.length,7);assert.equal(after.faces,7);assert.ok(after.edges>before.edges);
 assert.ok(m.vertices.some(v=>Math.abs(v[2]-1)<1e-8));
});
test('sculpt uses smooth distance falloff and does not move distant vertices',()=>{
 const m=createMesh([[0,0,0],[1,0,0],[0,1,0],[10,10,10]],[[0,1,2]]);
 const far=m.vertices[3].slice();sculpt(m,[0,0,0],2,.5,'push');
 assert.ok(m.vertices[0][2]>0);assert.deepEqual(m.vertices[3],far);
});
test('repair removes degenerate and duplicate faces and splits non-manifold edges',()=>{
 const m=createMesh([[0,0,0],[1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,2,0]],[[0,1,2],[2,1,0],[0,1,3],[0,1,4],[0,2,5]]);
 const before=inspectMesh(m);assert.ok(before.nonManifoldEdges.length>0);assert.ok(before.degenerateFaces.length>0);
 const result=repairMesh(m);
 assert.equal(result.report.removedDuplicate,1);assert.equal(result.report.removedDegenerate,1);assert.equal(result.report.splitNonManifoldEdges,1);
 assert.equal(inspectMesh(result.mesh).nonManifoldEdges.length,0);
 assert.ok(result.mesh.faces.every(f=>f.every(i=>i>=0&&i<result.mesh.vertices.length)));
});
