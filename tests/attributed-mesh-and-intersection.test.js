import test from 'node:test';
import assert from 'node:assert/strict';
import {createAttributedMesh, mergeAttributedVertices, deleteAttributedFaces, extrudeAttributedFaces, rebuildAttributedFace, attributeAudit} from '../frontend/attributed-mesh-core.js';
import {detectSelfIntersections} from '../frontend/self-intersection.js';
import {moveVertices, mergeVertices as legacyMergeVertices, deleteFaces as legacyDeleteFaces, extrudeFaces as legacyExtrudeFaces, rebuildFace} from '../frontend/mesh-editing-core.js';

test('corner UVs survive geometric vertex merge across a UV seam',()=>{
 const m=createAttributedMesh({vertices:[[0,0,0],[1,0,0],[0,1,0],[1,0,0],[1,1,0],[0,1,0]],faces:[[0,1,2],[3,4,5]],materialSlots:['red','blue'],attributes:{corner:{uv:[[[0,0],[1,0],[0,1]],[[0.25,0],[1,1],[0.25,1]]],splitNormal:[[[0,0,1],[0,0,1],[0,0,1]],[[0,1,0],[0,1,0],[0,1,0]]]},face:{materialIndex:[0,1]},vertex:{color:[[1,0,0],[1,0,0],[1,0,0],[1,0,0],[1,0,0],[1,0,0]],skinWeights:[{root:1},{root:1},{root:1},{root:1},{root:1},{root:1}]}}});
 mergeAttributedVertices(m,1e-6);
 assert.equal(m.vertices.length,4);
 assert.deepEqual(m.attributes.corner.uv[1][0],[0.25,0]);
 assert.deepEqual(m.attributes.corner.splitNormal[1][0],[0,1,0]);
 assert.deepEqual(m.attributes.face.materialIndex,[0,1]);
 assert.equal(attributeAudit(m).domains.corner.length,2);
});
test('deleting faces deletes corresponding face and corner attributes',()=>{
 const m=createAttributedMesh({vertices:[[0,0,0],[1,0,0],[0,1,0],[1,1,0]],faces:[[0,1,2],[1,3,2]],attributes:{face:{materialIndex:[2,3]},corner:{uv:[[[0,0],[1,0],[0,1]],[[1,0],[1,1],[0,1]]]}}});
 deleteAttributedFaces(m,[0]); assert.deepEqual(m.attributes.face.materialIndex,[3]);assert.equal(m.attributes.corner.uv.length,1);
});
test('extrusion inherits material and corner attributes and reports custom domain',()=>{
 const m=createAttributedMesh({vertices:[[0,0,0],[1,0,0],[0,1,0]],faces:[[0,1,2]],attributes:{face:{materialIndex:[4]},corner:{uv:[[[0,0],[1,0],[0,1]]]},custom:{opaque:{domain:'unknown',values:[1]}}}});
 const result=extrudeAttributedFaces(m,[0],1,[0,0,1]); assert.ok(m.faces.length>1);assert.ok(m.attributes.face.materialIndex.every(x=>x===4));assert.ok(result.attributeReport.unsupported.includes('opaque'));
});
test('rebuild refuses to guess corner mapping',()=>{
 const m=createAttributedMesh({vertices:[[0,0,0],[1,0,0],[0,1,0]],faces:[[0,1,2]],attributes:{face:{materialIndex:[0]},corner:{uv:[[[0,0],[1,0],[0,1]]]}}});
 assert.throws(()=>rebuildAttributedFace(m,[0,1,2],{sourceFace:0}),/sourceCorners mapping is required/);
});
test('detects crossing non-adjacent triangles and coplanar overlap',()=>{
 const crossing={vertices:[[0,0,0],[2,0,0],[0,2,0],[0.5,0.5,-1],[0.5,0.5,1],[1.5,0.5,0]],faces:[[0,1,2],[3,4,5]]};
 assert.equal(detectSelfIntersections(crossing).count,1);
 const coplanar={vertices:[[0,0,0],[2,0,0],[0,2,0],[0.25,0.25,0],[1,0.25,0],[0.25,1,0]],faces:[[0,1,2],[3,4,5]]};
 assert.equal(detectSelfIntersections(coplanar).count,1);
});
test('adjacent triangles are excluded by documented default policy',()=>{
 const m={vertices:[[0,0,0],[1,0,0],[0,1,0],[1,1,0]],faces:[[0,1,2],[1,3,2]]};
 assert.equal(detectSelfIntersections(m).count,0);
 assert.equal(detectSelfIntersections(m,{includeAdjacent:true}).status,'completed');
});

test('shared-vertex triangles can still be tested for a crossing beyond the shared point',()=>{
 const m={vertices:[[0,0,0],[2,0,0],[0,2,0],[0.5,0.5,-1],[0.5,0.5,1]],faces:[[0,1,2],[0,3,4]]};
 assert.equal(detectSelfIntersections(m).count,0,'documented conservative default excludes shared-vertex pairs');
 const inclusive=detectSelfIntersections(m,{includeAdjacent:true});
 assert.equal(inclusive.status,'completed');
 assert.equal(inclusive.count,1,'opt-in inclusive mode must detect intersection beyond the shared vertex');
});

test('edge attributes are remapped when merged vertices collapse edge keys',()=>{
 const m=createAttributedMesh({vertices:[[0,0,0],[1,0,0],[1.000001,0,0],[0,1,0]],faces:[[0,1,3],[0,2,3]],attributes:{edge:{'1,3':{crease:0.5},'2,3':{crease:0.5}}}});
 mergeAttributedVertices(m,1e-4);
 assert.equal(m.vertices.length,3);
 assert.deepEqual(m.attributes.edge['1,2'],{crease:0.5});
});


test('legacy topology API dispatches to attribute-aware operations without dropping domains',()=>{
 const m=createAttributedMesh({vertices:[[0,0,0],[1,0,0],[0,1,0],[1,0,0]],faces:[[0,1,2]],materialSlots:['mat'],attributes:{vertex:{color:[[1,0,0],[0,1,0],[0,0,1],[0,1,0]],skinWeights:[{root:1},{root:1},{root:1},{root:1}]},face:{materialIndex:[0]},corner:{uv:[[[0,0],[1,0],[0,1]]]}}});
 moveVertices(m,[0],[0,0,0.1]);
 assert.equal(m.lastAttributeReport.dropped.length,0);
 legacyMergeVertices(m,1e-6,{vertexAttributePolicy:'first'});
 assert.ok(m.attributes.vertex.color.length===m.vertices.length);
 assert.ok(m.attributes.vertex.skinWeights.length===m.vertices.length);
 assert.equal(m.attributes.corner.uv.length,m.faces.length);
 assert.ok(m.lastAttributeReport);
 const second=createAttributedMesh({vertices:[[0,0,0],[1,0,0],[0,1,0],[1,1,0]],faces:[[0,1,2],[1,3,2]],attributes:{face:{materialIndex:[1,2]},corner:{uv:[[[0,0],[1,0],[0,1]],[[1,0],[1,1],[0,1]]]}}});
 legacyDeleteFaces(second,[0]);
 assert.deepEqual(second.attributes.face.materialIndex,[2]);
 legacyExtrudeFaces(second,[0],0.25);
 assert.ok(second.faces.length>1);
 assert.equal(second.attributes.face.materialIndex.length,second.faces.length);
 const source=createAttributedMesh({vertices:[[0,0,0],[1,0,0],[0,1,0],[1,1,0]],faces:[[0,1,2]],attributes:{face:{materialIndex:[7]},corner:{uv:[[[0,0],[1,0],[0,1]]]}}});
 rebuildFace(source,[1,3,2],{sourceFace:0,sourceCorners:[1,1,2]});
 assert.deepEqual(source.attributes.face.materialIndex,[7,7]);
 assert.equal(source.attributes.corner.uv[1].length,3);
});
