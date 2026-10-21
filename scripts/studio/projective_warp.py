"""Validated measured homographies and depth-preserving FFmpeg sampling.

Coordinates use image bounds: pixel (x,y) has normalized center
((x+.5)/width,(y+.5)/height). Matrices map input to output. GEQ receives their
inverse and samples associated color/alpha together, returning straight RGBA.
"""
from __future__ import annotations

import copy
import json
import math

COORDINATES = "normalized-image-xy-pixel-centers"
MAX_PLANAR_FRAMES = 240
MAX_WARP_PIXELS = 2_073_600
IDENTITY = [1., 0., 0., 0., 1., 0., 0., 0., 1.]


def number(value, label, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(label + " must be finite")
    if not low <= value <= high or integer and value != int(value):
        raise ValueError(label + " is outside its supported range")
    return int(value) if integer else float(value)


def invert(matrix):
    a,b,c,d,e,f,g,h,i = matrix
    co = [e*i-f*h, c*h-b*i, b*f-c*e, f*g-d*i, a*i-c*g, c*d-a*f,
          d*h-e*g, b*g-a*h, a*e-b*d]
    determinant = a*co[0]+b*co[3]+c*co[6]
    if abs(determinant) < 1e-10:
        raise ValueError("The planar transform is singular")
    return [v/determinant for v in co]


def multiply(left, right):
    return [sum(left[r*3+k]*right[k*3+c] for k in range(3)) for r in range(3) for c in range(3)]


def transform(matrix, point):
    x,y = point
    denominator = matrix[6]*x+matrix[7]*y+matrix[8]
    if abs(denominator) < 1e-8:
        raise ValueError("A planar transform crosses a projective horizon")
    return [(matrix[0]*x+matrix[1]*y+matrix[2])/denominator,
            (matrix[3]*x+matrix[4]*y+matrix[5])/denominator]


def validate_matrix(value):
    if not isinstance(value, list) or len(value) != 9:
        raise ValueError("A planar matrix needs nine finite coefficients")
    matrix = [number(v, "Homography coefficient", -128, 128) for v in value]
    if abs(matrix[8]) < 1e-8:
        raise ValueError("The homography must have a nonzero bottom-right coefficient")
    matrix = [v/matrix[8] for v in matrix]
    inverse = invert(matrix)
    if max(map(abs,matrix))*max(map(abs,inverse)) > 100000:
        raise ValueError("The planar transform is ill-conditioned")
    # A planar source canvas must not straddle infinity. Inverse samples can
    # cross a horizon outside the source; those pixels are rejected by GEQ.
    corners = [(0,0),(1,0),(1,1),(0,1)]
    denominators = [matrix[6]*x+matrix[7]*y+matrix[8] for x,y in corners]
    if min(denominators) <= 1e-4:
        raise ValueError("The planar transform crosses a source-canvas horizon")
    if any(abs(v) > 8 for p in corners for v in transform(matrix,p)):
        raise ValueError("The planar transform exceeds its bounded canvas")
    return matrix


def validate_quad(value):
    if not isinstance(value,list) or len(value)!=4:
        raise ValueError("Choose four corners around one textured plane")
    points=[]
    for point in value:
        if not isinstance(point,list) or len(point)!=2:
            raise ValueError("Each plane corner needs X and Y")
        points.append([number(v,"Plane corner",0,1) for v in point])
    crosses=[]
    for n in range(4):
        a,b,c=points[n],points[(n+1)%4],points[(n+2)%4]
        crosses.append((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))
    area=sum(points[n][0]*points[(n+1)%4][1]-points[(n+1)%4][0]*points[n][1] for n in range(4))/2
    if min(crosses)<=1e-4 or area<.015 or any(math.dist(points[n],points[(n+1)%4])<.025 for n in range(4)):
        raise ValueError("Plane corners must form a nondegenerate clockwise convex quad, starting at top left")
    return points


def quad_matrix(quad):
    """Unit-square to convex quad, independently solved without OpenCV."""
    q=validate_quad(quad)
    x0,y0=q[0];x1,y1=q[1];x2,y2=q[2];x3,y3=q[3]
    dx1,dx2,dy1,dy2=x1-x2,x3-x2,y1-y2,y3-y2
    sx,sy=x0-x1+x2-x3,y0-y1+y2-y3
    divisor=dx1*dy2-dx2*dy1
    if abs(divisor)<1e-10:raise ValueError("The corner-pin quad is degenerate")
    g,h=(sx*dy2-dx2*sy)/divisor,(dx1*sy-sx*dy1)/divisor
    return validate_matrix([x1-x0+g*x1,x3-x0+h*x3,x0,
                            y1-y0+g*y1,y3-y0+h*y3,y0,g,h,1])


def validate_planar_motion(value, animation_start=0, animation_duration=None):
    if value is None:return None
    allowed={"version","mode","coordinates","canvas","keys","outside","source","invalidated"}
    if not isinstance(value,dict) or set(value)-allowed or type(value.get("version")) is not int or value["version"]!=1:
        raise ValueError("Unsupported planar motion document")
    mode=value.get("mode")
    if mode not in {"stabilize","corner_pin"} or value.get("coordinates")!=COORDINATES:
        raise ValueError("Planar motion needs its declared mode and pixel-center coordinate convention")
    if value.get("outside")!=("identity" if mode=="stabilize" else "transparent"):
        raise ValueError("Planar motion has an unsupported outside-range behavior")
    invalidated=value.get("invalidated")
    if invalidated is not None and (not isinstance(invalidated,str) or not invalidated.strip() or len(invalidated)>320):
        raise ValueError("Invalidated planar motion needs a bounded explanation")
    canvas=value.get("canvas")
    if not isinstance(canvas,dict) or set(canvas)!={"width","height"}:raise ValueError("Planar motion needs its source canvas")
    canvas={key:number(canvas[key],"Planar canvas",16,32768,True) for key in ("width","height")}
    keys=value.get("keys")
    if not isinstance(keys,list) or not 1<=len(keys)<=MAX_PLANAR_FRAMES:raise ValueError("Planar motion needs 1–240 measured frames")
    result=[];previous=None
    # Preserve measured keys through incompatible timing edits for undo and
    # save/reopen. Invalidated keys never execute, even if their new domain is
    # otherwise valid. Export separately requires remeasurement or removal.
    lower=-1_296_000 if invalidated else animation_start
    upper=1_296_000 if invalidated or animation_duration is None else animation_duration-1
    for key in keys:
        if not isinstance(key,dict) or set(key)!={"frame","matrix"}:raise ValueError("Planar keys need only an exact frame and matrix")
        frame=number(key["frame"],"Planar frame",lower,upper,True)
        if previous is not None and frame!=previous+1:raise ValueError("Planar motion cannot hide or interpolate missing frames")
        result.append({"frame":frame,"matrix":validate_matrix(key["matrix"])})
        previous=frame
    source=value.get("source")
    if not isinstance(source,dict) or len(json.dumps(source,allow_nan=False).encode())>16384:
        raise ValueError("Planar source identity is missing or oversized")
    normalized={"version":1,"mode":mode,"coordinates":COORDINATES,"canvas":canvas,
                "keys":result,"outside":value["outside"],"source":copy.deepcopy(source)}
    if invalidated:normalized["invalidated"]=invalidated
    return normalized


def compile_planar_warp(motion, animation_offset, width, height, pixel_format="rgba"):
    """Normalize to the supplied fixed canvas, warp, and return straight RGBA.

    Caller supplies fitted dimensions *before* authored transforms and derives
    corner-pin layout aspect from motion.canvas rather than the overlay image.
    Exact measured keys use the preserved animation frame N+animation_offset.
    """
    motion=validate_planar_motion(motion,animation_start=-1_296_000)
    width=number(width,"Planar output width",2,8192,True)
    height=number(height,"Planar output height",2,8192,True)
    if width*height>MAX_WARP_PIXELS:raise ValueError("Planar warping is bounded to 2,073,600 pixels")
    if pixel_format not in {"rgba","gbrap16le"}:raise ValueError("Planar warping requires explicit rgba or gbrap16le precision")
    if motion.get("invalidated"):
        if motion["mode"]=="stabilize":return []
        # A stale derived overlay must not turn into an unwarped full-frame
        # image. Preserve the authored clip but make its paused preview empty.
        planar="gbrap16le" if pixel_format=="gbrap16le" else "gbrap"
        return [f"format={planar}","geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='0'",f"format={pixel_format}"]
    offset=number(animation_offset,"Planar animation offset",-1_296_000,1_296_000,True)
    keys=motion["keys"];inverses=[invert(k["matrix"]) for k in keys]
    frame=f"(N+({offset}))"
    def expression(component,lo=0,hi=None):
        hi=len(keys) if hi is None else hi
        if hi-lo==1:return format(inverses[lo][component],'.15g')
        mid=(lo+hi)//2
        return f"if(lt({frame},{keys[mid]['frame']}),{expression(component,lo,mid)},{expression(component,mid,hi)})"
    # Ten GEQ registers: load H, then reuse consumed coefficients for the
    # coordinate/weight calculation. Explicit nearest samples avoid GEQ's
    # bilinear implementation incorrectly clamping the last row/column.
    steps=[f"st({n},{expression(n)})" for n in range(9)]
    steps += ["st(9,ld(6)*(X+0.5)/W+ld(7)*(Y+0.5)/H+ld(8))",
              "st(0,W*(ld(0)*(X+0.5)/W+ld(1)*(Y+0.5)/H+ld(2))/ld(9)-0.5)",
              "st(1,H*(ld(3)*(X+0.5)/W+ld(4)*(Y+0.5)/H+ld(5))/ld(9)-0.5)",
              "st(8,gt(abs(ld(9)),0.00000001)*between(ld(0),0,W-1)*between(ld(1),0,H-1))",
              "st(2,floor(ld(0)))","st(3,min(ld(2)+1,W-1))","st(4,floor(ld(1)))",
              "st(5,min(ld(4)+1,H-1))","st(6,ld(0)-ld(2))","st(7,ld(1)-ld(4))"]
    setup=';'.join(steps)
    active=f"between({frame},{keys[0]['frame']},{keys[-1]['frame']})"
    channels=[]
    for name,function in (("r","r"),("g","g"),("b","b"),("a","alpha")):
        outside=f"{function}(X,Y)" if motion["outside"]=="identity" else "0"
        sample=(f"{function}(ld(2),ld(4))*(1-ld(6))*(1-ld(7))+"
                f"{function}(ld(3),ld(4))*ld(6)*(1-ld(7))+"
                f"{function}(ld(2),ld(5))*(1-ld(6))*ld(7)+"
                f"{function}(ld(3),ld(5))*ld(6)*ld(7)")
        channels.append(f"{name}='{setup};if({active},if(ld(8),{sample},0),{outside})'")
    planar="gbrap16le" if pixel_format=="gbrap16le" else "gbrap"
    return [f"scale={width}:{height}:flags=lanczos",f"format={planar}","premultiply=inplace=1",
            "geq="+":".join(channels)+":interpolation=nearest","unpremultiply=inplace=1",f"format={pixel_format}"]
