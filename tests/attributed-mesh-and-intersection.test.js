import test from 'node:test';
import assert from 'node:assert/strict';
import {createAttributedMesh, mergeAttributedVertices, deleteAttributedFaces, extrudeAttributedFaces, rebuildAttributedFace, attributeAudit} from '../frontend/attributed-mesh-core.js';
import {detectSelfIntersections} from '../frontend/self-intersection.js';

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
