"""Independent triangle self-intersection counter for Blender mesh data.

Broad phase: x-axis AABB sweep + full 3D AABB rejection.
Narrow phase: segment/triangle intersection and dominant-axis coplanar 2D overlap.
Triangles sharing vertex indices are skipped by default to avoid expected adjacency.
Degenerate triangles are excluded and counted separately by mesh quality metrics.
"""
from math import sqrt


def _sub(a, b): return tuple(a[i] - b[i] for i in range(3))
def _dot(a, b): return sum(a[i] * b[i] for i in range(3))
def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def _norm(a): return sqrt(_dot(a, a))
def _orient(a, b, c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def _project(p, axis): return (p[(axis+1)%3], p[(axis+2)%3]) if axis != 1 else (p[0], p[2])
def _on_segment(p, a, b, e):
    return min(a[0],b[0])-e <= p[0] <= max(a[0],b[0])+e and min(a[1],b[1])-e <= p[1] <= max(a[1],b[1])+e

def _segments2(a,b,c,d,e):
    o1,o2,o3,o4 = _orient(a,b,c),_orient(a,b,d),_orient(c,d,a),_orient(c,d,b)
    if ((o1>e and o2 < -e) or (o1 < -e and o2>e)) and ((o3>e and o4 < -e) or (o3 < -e and o4>e)): return True
    return ((abs(o1)<=e and _on_segment(c,a,b,e)) or (abs(o2)<=e and _on_segment(d,a,b,e)) or
            (abs(o3)<=e and _on_segment(a,c,d,e)) or (abs(o4)<=e and _on_segment(b,c,d,e))

def _point_tri2(p,t,e):
    v = (_orient(t[0],t[1],p),_orient(t[1],t[2],p),_orient(t[2],t[0],p))
    return min(v)>=-e or max(v)<=e

def _coplanar(a,b,n,e):
    axis=max(range(3),key=lambda i:abs(n[i]))
    A=[_project(p,axis) for p in a]; B=[_project(p,axis) for p in b]
    for i in range(3):
        for j in range(3):
            if _segments2(A[i],A[(i+1)%3],B[j],B[(j+1)%3],e): return True
    return _point_tri2(A[0],B,e) or _point_tri2(B[0],A,e)

def _segment_triangle(p,q,t,e):
    d=_sub(q,p); e1=_sub(t[1],t[0]); e2=_sub(t[2],t[0]); h=_cross(d,e2); det=_dot(e1,h)
    if abs(det)<=e: return False
    inv=1.0/det; s=_sub(p,t[0]); u=inv*_dot(s,h)
    if u < -e or u > 1+e: return False
    r=_cross(s,e1); v=inv*_dot(d,r)
    if v < -e or u+v > 1+e: return False
    x=inv*_dot(e2,r)
    return -e <= x <= 1+e

def _hit(a,b,e):
    na=_cross(_sub(a[1],a[0]),_sub(a[2],a[0])); nb=_cross(_sub(b[1],b[0]),_sub(b[2],b[0]))
    if _norm(na)<=e or _norm(nb)<=e: return False
    parallel=_norm(_cross(na,nb)) <= e*_norm(na)*_norm(nb)
    if parallel and abs(_dot(na,_sub(b[0],a[0]))) <= e*_norm(na): return _coplanar(a,b,na,e)
    for i in range(3):
        if _segment_triangle(a[i],a[(i+1)%3],b,e) or _segment_triangle(b[i],b[(i+1)%3],a,e): return True
    return False

def count_self_intersections(vertices, faces, epsilon=1e-8):
    """Return stable face-pair counts and policy metadata for triangulated faces."""
    triangles=[]
    for face_index, face in enumerate(faces):
        # Blender mesh polygons may be n-gons; triangulate as a fan for diagnostics.
        for i in range(1,len(face)-1):
            ids=(face[0],face[i],face[i+1]); pts=tuple(tuple(float(x) for x in vertices[k]) for k in ids)
            n=_cross(_sub(pts[1],pts[0]),_sub(pts[2],pts[0]))
            if _norm(n)<=epsilon: continue
            triangles.append({"face":face_index,"ids":ids,"p":pts,
              "min":tuple(min(p[k] for p in pts) for k in range(3)),
              "max":tuple(max(p[k] for p in pts) for k in range(3))})
    order=sorted(range(len(triangles)),key=lambda i:triangles[i]["min"][0]); active=[]; pairs=set()
    for idx in order:
        t=triangles[idx]
        active=[j for j in active if triangles[j]["max"][0]>=t["min"][0]-epsilon]
        for j in active:
            u=triangles[j]
            if set(t["ids"]) & set(u["ids"]): continue
            if any(t["min"][k]>u["max"][k]+epsilon or u["min"][k]>t["max"][k]+epsilon for k in (1,2)): continue
            if _hit(t["p"],u["p"],epsilon) and t["face"] != u["face"]:
                pairs.add(tuple(sorted((t["face"],u["face"]))))
        active.append(idx)
    return {"status":"completed","count":len(pairs),"pairs":[list(p) for p in sorted(pairs)],
            "policy":{"epsilon_model_units":epsilon,"adjacency":"skip triangle pairs sharing vertex indices",
                      "coplanar":"dominant-axis 2D overlap/touch counts as intersection",
                      "degenerate_triangles":"excluded","broad_phase":"x-axis AABB sweep + 3D AABB",
                      "narrow_phase":"segment-triangle + coplanar 2D overlap"}}
