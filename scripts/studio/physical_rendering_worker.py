"""Actual Mitsuba/Dr.Jit CPU worker. Invoked only with python -I -B.

All dictionaries passed to Mitsuba are constructed here from a closed typed
recipe. There is no XML loader, expression evaluator, network access or user
selected plugin. PBRT only receives our generated file in the owned job cwd.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from physical_rendering import (PBRT_SCOPE, VARIANTS, _flatten_mesh, _hash_file, _json,
                                _validate_scene_support, _world_mesh, area_mesh, geometry_mesh,
                                material_emission, scale_spectrum, srgb_to_linear, validate_settings)
from scene import camera_basis_at, focal_length_mm, object_matrix_at, pose_at, validate_scene


def _engine(mode):
    try:
        import mitsuba as mi
        import drjit as dr
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Mitsuba, Dr.Jit and NumPy must be installed in the optional physical runtime: " + str(exc)) from exc
    variant=VARIANTS[mode]
    if variant not in mi.variants():raise RuntimeError("The installed Mitsuba does not provide "+variant)
    mi.set_variant(variant)
    if not dr.has_backend(dr.JitBackend.LLVM):
        raise RuntimeError("Dr.Jit's LLVM CPU backend is unavailable. Install LLVM and configure CINEMATICUM_PHYSICAL_LLVM.")
    dr.set_thread_count(2)
    # Actually compile/evaluate one CPU kernel, rather than treating an import as availability.
    value=dr.sum(dr.arange(mi.Float,17)*2)
    dr.eval(value)
    if float(value[0])!=272:raise RuntimeError("The LLVM CPU kernel probe returned invalid data.")
    return mi,dr,np


def doctor():
    modes=[];versions={}
    for mode in VARIANTS:
        mi,dr,np=_engine(mode)
        integrator={"type":"stokes","integrator":{"type":"volpath"}} if mode=="polarized" else {"type":"prb" if mode=="rgb" else "path"}
        mi.load_dict(integrator)
        modes.append(mode)
        versions={"python":sys.version.split()[0],"mitsuba":mi.__version__,"drjit":dr.__version__,"numpy":np.__version__,
                  "llvm":list(dr.detail.llvm_version())}
    return {"available":True,"modes":modes,"versions":versions}


def install_probe():
    """Small actual CPU radiance/AD gates before publishing a managed runtime."""
    from physical_rendering import default_settings
    from scene import default_scene
    checks={};metrics={};report=doctor()
    scene=default_scene(16,16);scene["camera"].update(position=[0,0,4],target=[0,0,0],fov=10)
    scene["lights"]=[];scene["objects"]=[{"id":"surface","name":"Surface","type":"plane",
        "position":[0,0,0],"rotation":[0,0,0],"scale":[5,5,1]}]
    scene=validate_scene(scene);settings=default_settings();settings.update(mode="rgb",spp=64,
        world_spectrum={"type":"uniform","value":1},material_overrides={"surface":{"type":"diffuse",
        "reflectance":{"type":"rgb","value":[.2,.4,.6]}}})
    settings=validate_settings(settings,scene);mi,dr,np=_engine("rgb")
    rendered=build_scene(scene,settings,mi,np,inverse=True);params=mi.traverse(rendered)
    key=next(k for k in params.keys() if k.endswith("reflectance.value"))
    dr.enable_grad(params[key]);params.update();image=mi.render(rendered,params,spp=64,seed=7)
    average=np.mean(np.asarray(image),axis=(0,1));dr.backward(dr.mean(image));gradient=np.asarray(dr.grad(params[key])).ravel()
    checks["actual_rgb_radiance"]=bool(np.max(np.abs(average-np.array([.2,.4,.6])))<.025)
    checks["actual_reverse_mode_gradient"]=bool(np.isfinite(gradient).all() and np.max(np.abs(gradient-1/3))<.03)
    metrics.update(rgb_mean=average.tolist(),rgb_gradient=gradient.tolist())
    mi,dr,np=_engine("spectral");scene["objects"]=[]
    settings.update(mode="spectral",material_overrides={},world_spectrum={"type":"sampled",
        "wavelengths":[360,590,600,640,650,830],"values":[0,0,1,1,0,0]},
        spectral_bands=[{"name":"blue","min_nm":400,"max_nm":500},{"name":"red","min_nm":600,"max_nm":640}])
    rendered=build_scene(scene,settings,mi,np,band_film=True);mi.render(rendered,spp=64,seed=7)
    values=np.mean(np.asarray(rendered.sensors()[0].film().bitmap(raw=False)),axis=(0,1))
    checks["actual_spectral_integral"]=bool(abs(values[0])<1e-6 and abs(values[1]-40)<.15);metrics["spectral_band_integrals"]=values.tolist()
    mi,dr,np=_engine("polarized");scene["objects"]=[{"id":"surface","name":"Polarizer","type":"plane",
        "position":[0,0,0],"rotation":[0,0,0],"scale":[5,5,1]}]
    settings.update(mode="polarized",spectral_bands=[],world_spectrum={"type":"uniform","value":1},
        material_overrides={"surface":{"type":"polarizer","angle":0,"transmittance":1}})
    rendered=build_scene(validate_scene(scene),settings,mi,np);mi.render(rendered,spp=64,seed=7)
    bitmap=rendered.sensors()[0].film().bitmap(raw=False);values=np.mean(np.asarray(bitmap),axis=(0,1))
    checks["actual_polarized_stokes"]=bool(len(values)==15 and np.isfinite(values).all() and np.sum(values[3:6])>1 and
        np.max(np.abs(values[3:6]-values[6:9]))<1e-5)
    metrics["stokes_mean"]=values.tolist()
    if not all(checks.values()):raise RuntimeError("The installed renderer failed real CPU physical acceptance: "+json.dumps(checks))
    return {**report,"checks":checks,"metrics":metrics,"scope":"Small CPU radiance, spectrum, Stokes and gradient acceptance; not production convergence or full renderer parity."}


def spectrum(value):
    if value["type"] in {"rgb","uniform"}:return {"type":value["type"],"value":value["value"]}
    return {"type":"irregular","wavelengths":", ".join(map(str,value["wavelengths"])),
            "values":", ".join(map(str,value["values"]))}


def _bsdf(obj,settings):
    override=settings["material_overrides"].get(obj["id"])
    if override:
        kind=override["type"]
        if kind=="diffuse":return {"type":"diffuse","reflectance":spectrum(override["reflectance"])}
        if kind=="coated_diffuse":
            result={"type":"roughplastic" if override["roughness"] else "plastic",
                    "diffuse_reflectance":spectrum(override["reflectance"]),"int_ior":override["ior"],"ext_ior":1.}
            if override["roughness"]:result.update(distribution="ggx",alpha=override["roughness"])
            return result
        if kind=="dielectric":
            result={"type":"roughdielectric" if override["roughness"] else "dielectric","int_ior":override["ior"],"ext_ior":1.}
            if override["roughness"]:result.update(distribution="ggx",alpha=override["roughness"])
            return result
        if kind=="conductor":
            result={"type":"roughconductor" if override["roughness"] else "conductor","eta":spectrum(override["eta"]),"k":spectrum(override["k"])}
            if override["roughness"]:result.update(distribution="ggx",alpha=override["roughness"])
            return result
        if kind in {"polarizer","retarder"}:
            result={"type":kind,"theta":override["angle"],"transmittance":override["transmittance"]}
            if kind=="retarder":result["delta"]=override["retardance"]
            return result
        raise ValueError("Unsupported physical BSDF.")
    m=obj["material"]
    return {"type":"principled","base_color":{"type":"rgb","value":srgb_to_linear(m["color"])},
            "roughness":m["roughness"],"metallic":m["metallic"],"spec_trans":m["transmission"],"eta":m["ior"]}


def _mesh(mi,np,name,geometry,bsdf,emission=None):
    flat=_flatten_mesh(geometry)
    props=mi.Properties();props["bsdf"]=mi.load_dict({**bsdf,"id":"material_"+name})
    if emission:props["emitter"]=mi.load_dict({"type":"area","radiance":spectrum(emission)})
    mesh=mi.Mesh(name,len(flat["vertices"]),len(flat["triangles"]),props,
                 has_vertex_normals=bool(flat["normals"]),has_vertex_texcoords=bool(flat["uvs"]))
    params=mi.traverse(mesh)
    params["vertex_positions"]=np.asarray(flat["vertices"],dtype=np.float32).ravel()
    params["faces"]=np.asarray(flat["triangles"],dtype=np.uint32).ravel()
    if flat["normals"]:params["vertex_normals"]=np.asarray(flat["normals"],dtype=np.float32).ravel()
    if flat["uvs"]:params["vertex_texcoords"]=np.asarray(flat["uvs"],dtype=np.float32).ravel()
    params.update()
    return mesh


def build_scene(scene,settings,mi,np,band_film=False,inverse=False):
    frame=settings["frame"];camera=pose_at(scene["camera"],frame,"camera");basis=camera_basis_at(scene["camera"],frame)
    film={"type":"specfilm" if band_film else "hdrfilm","width":scene["width"],"height":scene["height"],
          "component_format":"float32","rfilter":{"type":"box"}}
    if band_film:
        for band in settings["spectral_bands"]:
            film[band["name"]]={"type":"regular","wavelength_min":band["min_nm"],"wavelength_max":band["max_nm"],"values":"1,1"}
    else:film["pixel_format"]="rgb"
    sensor={"type":"thinlens" if scene["camera"]["dof_enabled"] else "perspective","fov":camera["fov"],"fov_axis":"y",
            "to_world":mi.ScalarAffineTransform4f().look_at(origin=camera["position"],target=camera["target"],up=basis["up"]),
            "principal_point_offset_x":-camera["shift_x"],"principal_point_offset_y":camera["shift_y"],
            "near_clip":.0001,"far_clip":10000000.,"film":film,"sampler":{"type":"independent"}}
    if scene["camera"]["dof_enabled"]:
        sensor.update(aperture_radius=focal_length_mm(scene["camera"],camera["fov"])/1000/(2*camera["f_stop"]),
                      focus_distance=camera["focus_distance"])
    integrator={"type":"prb" if inverse else ("volpath" if settings["mode"]=="polarized" else "path"),"max_depth":settings["max_depth"]}
    if settings["mode"]=="polarized":integrator={"type":"stokes","integrator":integrator}
    world=settings["world_spectrum"] or {"type":"rgb","value":[v*scene["world"]["strength"] for v in srgb_to_linear(scene["world"]["color"])]}
    data={"type":"scene","integrator":integrator,"sensor":sensor,"world":{"type":"constant","radiance":spectrum(world)}}
    for obj in scene["objects"]:
        name="object_"+obj["id"]
        geometry=_world_mesh(geometry_mesh(obj),object_matrix_at(scene,obj["id"],frame))
        data[name]=_mesh(mi,np,name,geometry,_bsdf(obj,settings),material_emission(obj,settings))
    for light in scene["lights"]:
        name="light_"+light["id"];p=pose_at(light,frame,"light")
        color=settings["light_spectra"].get(light["id"],{"type":"rgb","value":srgb_to_linear(light["color"])})
        if light["type"]=="point":
            data[name]={"type":"point","position":p["position"],"intensity":spectrum(scale_spectrum(color,p["power"]/(4*math.pi)))}
        elif light["type"]=="sun":
            data[name]={"type":"directional","direction":[t-f for t,f in zip(p["target"],p["position"])],"irradiance":spectrum(scale_spectrum(color,p["power"]))}
        else:
            data[name]=_mesh(mi,np,name,area_mesh(p),{"type":"diffuse","reflectance":0.},scale_spectrum(color,p["power"]/(math.pi*p["size"]**2)))
    return mi.load_dict(data)


def _progress(path,value):
    dest=Path(path);temporary=dest.with_name(dest.name+".tmp")
    temporary.write_bytes(_json({"progress":value}));os.replace(temporary,dest)


def _metrics(array,channels,np):
    if not np.isfinite(array).all():raise RuntimeError("Physical renderer produced nonfinite radiance.")
    return {"width":int(array.shape[1]),"height":int(array.shape[0]),"channels":list(channels),"dtype":str(array.dtype),
            "min":float(np.min(array)),"max":float(np.max(array)),"mean":[float(v) for v in np.mean(array,axis=(0,1))],
            "finite":True}


def _preview(rgb,path,mi,np):
    rgb=np.ascontiguousarray(rgb,dtype=np.float32)
    if rgb.shape[-1]!=3 or not np.isfinite(rgb).all():raise RuntimeError("Invalid RGB preview source.")
    # This viewing image is clipped, while the independent float32 EXR stays linear/unclipped.
    mi.Bitmap(rgb).convert(mi.Bitmap.PixelFormat.RGB,mi.Struct.Type.UInt8,True).write(str(path))


def _bitmap_channels(bitmap):
    return [field.name for field in bitmap.struct_()]


def _write_render(rendered,output,mi,np):
    bitmap=rendered.sensors()[0].film().bitmap(raw=False)
    array=np.asarray(bitmap)
    metrics=_metrics(array,_bitmap_channels(bitmap),np)
    bitmap.write(str(output/"render.exr"))
    _preview(array[:,:,:3],output/"preview.png",mi,np)
    return metrics


def _target_image(path,scene,mi,np):
    bitmap=mi.Bitmap(str(path))
    if bitmap.width()!=scene["width"] or bitmap.height()!=scene["height"]:
        raise ValueError("Inverse target dimensions must equal the authored scene; implicit resize is not permitted.")
    if bitmap.pixel_format() not in {mi.Bitmap.PixelFormat.RGB,mi.Bitmap.PixelFormat.RGBA,mi.Bitmap.PixelFormat.Y,mi.Bitmap.PixelFormat.YA}:
        raise ValueError("Inverse targets require a plain RGB/RGBA or gray still; arbitrary EXR channels are unsupported.")
    rgba=np.array(bitmap.convert(mi.Bitmap.PixelFormat.RGBA,mi.Struct.Type.Float32,False))
    if not np.isfinite(rgba).all() or np.max(np.abs(rgba))>1e8:raise ValueError("Inverse target contains nonfinite or excessive pixel values.")
    if not np.all(np.abs(rgba[:,:,3]-1)<1e-6):raise ValueError("Inverse targets must be opaque; alpha-composited target fitting is unsupported.")
    return np.ascontiguousarray(rgba[:,:,:3]),"linear-sRGB" if Path(path).suffix.lower()==".exr" else "sRGB decoded to linear-sRGB"


def inverse(scene,settings,target_path,output,progress,mi,dr,np):
    rendered=build_scene(scene,settings,mi,np,inverse=True);params=mi.traverse(rendered)
    object_id=settings["optimization"]["object_id"]
    candidates=[key for key in params.keys() if key in {"object_"+object_id+".bsdf.reflectance.value","material_object_"+object_id+".reflectance.value"}]
    if len(candidates)!=1:raise RuntimeError("The renderer did not expose the selected diffuse RGB reflectance parameter.")
    key=candidates[0]
    target,encoding=_target_image(target_path,scene,mi,np);target_tensor=mi.TensorXf(target)
    initial=np.array(params[key]).reshape(-1).tolist();best_value=list(initial)
    evaluation_seed=(settings["seed"]+104729)%2147483647
    def evaluate():
        image=mi.render(rendered,params,spp=settings["spp"],seed=evaluation_seed)
        loss=float(dr.mean(dr.square(image-target_tensor)).array[0])
        if not math.isfinite(loss):raise RuntimeError("Inverse rendering produced a nonfinite objective.")
        return loss
    initial_loss=evaluate();best_loss=initial_loss
    opt=dr.opt.Adam(lr=settings["optimization"]["learning_rate"])
    opt[key]=params[key];params.update(opt)
    history=[];gradients=[];iterations=settings["optimization"]["iterations"]
    for iteration in range(iterations):
        image=mi.render(rendered,params,spp=settings["spp"],seed=(settings["seed"]+iteration)%2147483647)
        loss=dr.mean(dr.square(image-target_tensor));dr.backward(loss)
        gradient=np.array(dr.grad(opt[key])).reshape(-1)
        if not np.isfinite(gradient).all():raise RuntimeError("Inverse rendering produced a nonfinite actual image gradient.")
        gradients.append(gradient.tolist())
        training_loss=float(loss.array[0]);opt.step();opt[key]=dr.clip(opt[key],0.,1.);params.update(opt)
        with dr.suspend_grad():objective=evaluate()
        if objective<best_loss:
            best_loss=objective;best_value=np.array(params[key]).reshape(-1).tolist()
        history.append({"iteration":iteration+1,"training_loss":training_loss,"evaluation_loss":objective,"best_loss":best_loss})
        _progress(progress,.1+.8*(iteration+1)/iterations)
    params[key]=mi.Color3f(best_value);params.update()
    mi.render(rendered,spp=settings["spp"],seed=evaluation_seed)
    metrics=_write_render(rendered,output,mi,np)
    final_loss=float(np.mean((np.asarray(rendered.sensors()[0].film().bitmap(raw=False))-target)**2))
    if not math.isfinite(final_loss):raise RuntimeError("Final inverse loss is not finite.")
    optimized=copy.deepcopy(settings);optimized["material_overrides"][object_id]["reflectance"]={"type":"rgb","value":best_value}
    optimized=validate_settings(optimized,scene)
    report={"parameter":key,"object_id":object_id,"initial_value":initial,"final_value":best_value,
            "initial_loss":initial_loss,"final_loss":final_loss,"iterations":iterations,"loss":"mean squared linear RGB radiance error",
            "target_encoding":encoding,"evaluation_seed":evaluation_seed,"optimizer":"drjit.opt.Adam","history":history,"gradients":gradients,
            "selection":"Lowest fixed-seed evaluation loss including the initial value; explicit Apply is required to edit the project.",
            "scope":"Diffuse RGB material reflectance only; no geometry, camera, texture, spectral-curve or occlusion optimization."}
    (output/"optimization.json").write_bytes(_json(report));(output/"optimized-settings.json").write_bytes(_json(optimized))
    return {"optimized_settings":optimized,"metrics":{**metrics,"optimization":{k:report[k] for k in ("initial_loss","final_loss","iterations","initial_value","final_value")}}}


def _pbrt_render(request,output,mi,np):
    binary=Path(request["pbrt"])
    # The parent selected the executable; the scene comes exclusively from the typed serializer.
    binary_sha,size=_hash_file(binary,1024*1024*1024)
    before=hashlib.sha256((output/"scene.pbrt").read_bytes()).hexdigest()
    with (output.parent/"pbrt.stdout").open("wb") as stdout,(output.parent/"pbrt.stderr").open("wb") as stderr:
        process=subprocess.run([str(binary),"--nthreads","2","scene.pbrt"],cwd=output,stdin=subprocess.DEVNULL,
                               stdout=stdout,stderr=stderr,timeout=540)
    diagnostics=(output.parent/"pbrt.stderr").read_text(errors="replace")
    banner=(output.parent/"pbrt.stdout").read_text(errors="replace")
    if process.returncode:raise RuntimeError("PBRT rendering failed: "+diagnostics[-1400:])
    if "pbrt version 4" not in banner.lower():raise RuntimeError("The executable did not identify itself as PBRT version 4.")
    if hashlib.sha256((output/"scene.pbrt").read_bytes()).hexdigest()!=before:raise RuntimeError("PBRT altered the retained scene input.")
    bitmap=mi.Bitmap(str(output/"render.exr"));linear=bitmap.convert(mi.Bitmap.PixelFormat.RGB,mi.Struct.Type.Float32,False)
    array=np.asarray(linear);metrics=_metrics(array,_bitmap_channels(linear),np)
    if array.shape!=(request["scene"]["height"],request["scene"]["width"],3):raise RuntimeError("PBRT output dimensions or channels differ from the scene.")
    _preview(array,output/"preview.png",mi,np)
    return {"engine":{"name":"pbrt-v4","binary_sha256":binary_sha,"binary_bytes":size,"cpu_threads":2,
                       "postprocess_mitsuba":mi.__version__},"metrics":metrics,"scope":PBRT_SCOPE}


def render(request):
    scene=validate_scene(request["scene"]);_validate_scene_support(scene)
    recipe=request["recipe"];settings=validate_settings(recipe["settings"],scene)
    output=Path(request["output_dir"])
    if not output.is_dir() or output.is_symlink():raise ValueError("Physical output directory is invalid.")
    mi,dr,np=_engine(settings["mode"])
    engine={"name":"Mitsuba","version":mi.__version__,"drjit":dr.__version__,"numpy":np.__version__,
            "variant":mi.variant(),"cpu_threads":2,"python":sys.version.split()[0]}
    _progress(request["progress_path"],.05)
    if recipe["operation"]=="pbrt_render":return _pbrt_render(request,output,mi,np)
    if recipe["operation"]=="inverse":
        result=inverse(scene,settings,request["target_path"],output,request["progress_path"],mi,dr,np)
    else:
        rendered=build_scene(scene,settings,mi,np)
        mi.render(rendered,spp=settings["spp"],seed=settings["seed"])
        result={"metrics":_write_render(rendered,output,mi,np)}
        _progress(request["progress_path"],.65)
        if settings["spectral_bands"]:
            spectral_scene=build_scene(scene,settings,mi,np,band_film=True)
            mi.render(spectral_scene,spp=settings["spp"],seed=settings["seed"])
            bitmap=spectral_scene.sensors()[0].film().bitmap(raw=False)
            result["metrics"]["spectral"]=_metrics(np.asarray(bitmap),_bitmap_channels(bitmap),np)
            bitmap.write(str(output/"spectral.exr"))
    result["engine"]=engine
    result["scope"]={"single_frame":settings["frame"],"movie_pipeline":False,"display":"Clipped sRGB PNG; float32 OpenEXR radiance remains unclipped.",
                     "rgb_spectra":"RGB colors are reconstructed spectra in spectral modes; explicit sampled spectra preserve the supplied curve.",
                     "stokes":"S0..S3 each projected to linear RGB in the camera reference frame." if settings["mode"]=="polarized" else None,
                     "geometry":PBRT_SCOPE["primitive_geometry"],"lights":"One scene unit is a metre; point power/(4pi), square-area power/(pi*area), sun irradiance.",
                     "roughness":"Typed physical dielectric/conductor/coated-diffuse roughness is microfacet alpha (no PBRT remapping).",
                     "cycles_settings":"Cycles device, denoising and per-lobe bounces do not apply; this recipe's CPU mode, spp, max_depth and seed are authoritative."}
    return result


def main():
    try:
        raw=sys.stdin.buffer.read(24*1024*1024+1)
        if len(raw)>24*1024*1024:raise ValueError("Physical worker request exceeds 24 MiB.")
        request=json.loads(raw)
        if not isinstance(request,dict):raise ValueError("Physical worker request must be an object.")
        if request.get("command")=="doctor":result=doctor()
        elif request.get("command")=="install_probe":result=install_probe()
        elif request.get("command")=="render":result=render(request)
        else:raise ValueError("Unsupported physical worker command.")
        sys.stdout.write(json.dumps(result,allow_nan=False,sort_keys=True)+"\n")
    except Exception as exc:
        sys.stdout.write(json.dumps({"error":str(exc)},allow_nan=False)+"\n")
        return 1
    return 0


if __name__=="__main__":
    raise SystemExit(main())
