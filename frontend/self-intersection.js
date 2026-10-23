/**
 * Independent triangle self-intersection detector.
 * Uses an AABB sweep broad phase and triangle-triangle narrow phase.
 *
 * Policy:
 * - triangles sharing any vertex index are treated as adjacent and skipped;
 * - non-coplanar intersections are confirmed by segment/triangle tests;
 * - coplanar pairs are projected to their dominant plane and tested in 2D;
 * - epsilon is an absolute model-space tolerance, caller-configurable.
 * Degenerate triangles are excluded and must be reported by mesh quality metrics.
 */
const sub=(a,b)=>a.map((v,i)=>v-b[i]);
const dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const norm=a=>Math.hypot(...a);
const orient2=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
const project=(p,axis)=>axis===0?[p[1],p[2]]:axis===1?[p[0],p[2]]:[p[0],p[1]];
const onSegment=(p,a,b,e)=>Math.min(a[0],b[0])-e<=p[0]&&p[0]<=Math.max(a[0],b[0])+e&&Math.min(a[1],b[1])-e<=p[1]&&p[1]<=Math.max(a[1],b[1])+e;
function seg2(a,b,c,d,e){
 const o1=orient2(a,b,c),o2=orient2(a,b,d),o3=orient2(c,d,a),o4=orient2(c,d,b);
 if(((o1>e&&o2< -e)||(o1< -e&&o2>e))&&((o3>e&&o4< -e)||(o3< -e&&o4>e)))return true;
 return (Math.abs(o1)<=e&&onSegment(c,a,b,e))||(Math.abs(o2)<=e&&onSegment(d,a,b,e))||(Math.abs(o3)<=e&&onSegment(a,c,d,e))||(Math.abs(o4)<=e&&onSegment(b,c,d,e));
}
function pointTri2(p,t,e){const a=orient2(t[0],t[1],p),b=orient2(t[1],t[2],p),c=orient2(t[2],t[0],p);return (a>=-e&&b>=-e&&c>=-e)||(a<=e&&b<=e&&c<=e);}
function coplanar(a,b,normal,e){
 const axis=normal.map(Math.abs).indexOf(Math.max(...normal.map(Math.abs))), A=a.map(p=>project(p,axis)),B=b.map(p=>project(p,axis));
 for(let i=0;i<3;i++)for(let j=0;j<3;j++)if(seg2(A[i],A[(i+1)%3],B[j],B[(j+1)%3],e))return true;
 return pointTri2(A[0],B,e)||pointTri2(B[0],A,e);
}
function segmentTriangle(p,q,t,e){
 const d=sub(q,p),e1=sub(t[1],t[0]),e2=sub(t[2],t[0]),h=cross(d,e2),det=dot(e1,h);
 if(Math.abs(det)<=e)return null;
 const inv=1/det,s=sub(p,t[0]),u=inv*dot(s,h);
 if(u< -e||u>1+e)return null;
 const r=cross(s,e1),v=inv*dot(d,r);
 if(v< -e||u+v>1+e)return null;
 const x=inv*dot(e2,r);
 return x>=-e&&x<=1+e ? p.map((n,i)=>n+d[i]*x):null;
}
function triHit(a,b,e){
 const na=cross(sub(a[1],a[0]),sub(a[2],a[0])),nb=cross(sub(b[1],b[0]),sub(b[2],b[0]));
 if(norm(na)<=e||norm(nb)<=e)return false;
 const parallel=norm(cross(na,nb))<=e*norm(na)*norm(nb);
 if(parallel&&Math.abs(dot(na,sub(b[0],a[0])))<=e*norm(na))return coplanar(a,b,na,e);
 for(let i=0;i<3;i++)if(segmentTriangle(a[i],a[(i+1)%3],b,e)||segmentTriangle(b[i],b[(i+1)%3],a,e))return true;
 return false;
}
export function detectSelfIntersections(mesh,{epsilon=1e-8,includeAdjacent=false}={}){
 if(!mesh||!Array.isArray(mesh.vertices)||!Array.isArray(mesh.faces))throw new TypeError('mesh vertices/faces required');
 const tris=[];
 mesh.faces.forEach((face,faceIndex)=>{for(let i=1;i<face.length-1;i++){const ids=[face[0],face[i],face[i+1]],points=ids.map(id=>mesh.vertices[id]);if(points.every(p=>Array.isArray(p)&&p.length===3&&p.every(Number.isFinite))){const n=cross(sub(points[1],points[0]),sub(points[2],points[0]));if(norm(n)>epsilon){const min=[0,1,2].map(k=>Math.min(...points.map(p=>p[k]))),max=[0,1,2].map(k=>Math.max(...points.map(p=>p[k])));tris.push({faceIndex,ids,points,min,max});}}}});
 const order=tris.map((_,i)=>i).sort((i,j)=>tris[i].min[0]-tris[j].min[0]),active=[],pairs=[];
 for(const idx of order){const t=tris[idx];for(let k=active.length-1;k>=0;k--)if(tris[active[k]].max[0]<t.min[0]-epsilon)active.splice(k,1);for(const j of active){const u=tris[j];if([1,2].some(axis=>t.min[axis]>u.max[axis]+epsilon||u.min[axis]>t.max[axis]+epsilon))continue;if(!includeAdjacent&&t.ids.some(id=>u.ids.includes(id)))continue;if(triHit(t.points,u.points,epsilon))pairs.push({faceA:u.faceIndex,faceB:t.faceIndex,triangleA:j,triangleB:idx});}active.push(idx);}
 const unique=new Map();for(const p of pairs){const k=[p.faceA,p.faceB].sort((a,b)=>a-b).join(':');if(!unique.has(k))unique.set(k,p);}
 return {status:'completed',count:unique.size,pairs:[...unique.values()],policy:{epsilon,adjacentTriangles:includeAdjacent?'tested':'ignored_if_share_vertex',coplanar:'dominant-axis 2D overlap including touching',degenerateTriangles:'excluded; report separately',broadPhase:'x-axis sweep with 3D AABB overlap',narrowPhase:'segment-triangle and coplanar 2D tests'}};
}
