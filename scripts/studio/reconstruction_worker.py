"""Isolated, pinned CPU COLMAP worker. No project-controlled code or plugins."""
from __future__ import annotations

from contextlib import closing
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import sqlite3
import sys
import time
import warnings
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageOps
import pycolmap as colmap

PINS={"pycolmap":"4.2.1","numpy":"2.5.4","pillow":"13.0.0"}
Image.MAX_IMAGE_PIXELS=16*1024*1024
warnings.simplefilter("error",Image.DecompressionBombWarning)


def encoded(value):return (json.dumps(value,sort_keys=True,allow_nan=False,indent=2)+"\n").encode()


def versions():
    result={name:importlib.metadata.version(name) for name in PINS}
    if result!=PINS:raise RuntimeError("COLMAP runtime versions differ from the tested pinned package set.")
    return result


def progress(request,value,phase):
    path=Path(request["progress_path"]);temporary=path.with_suffix(".tmp")
    temporary.write_bytes(encoded({"progress":value,"phase":phase}));temporary.replace(path)


def reprojection(model):
    values=[]
    for image in model.images.values():
        if not image.has_pose:continue
        pose=image.cam_from_world()
        for point in image.points2D:
            if point.has_point3D():
                projected=image.camera.img_from_cam(pose*model.points3D[point.point3D_id].xyz)
                if projected is None or not np.isfinite(projected).all():raise ValueError("A solved point has an invalid camera projection.")
                values.append(float(np.linalg.norm(projected-point.xy)))
    if not values:raise ValueError("COLMAP produced no measured reprojections.")
    data=np.array(values)
    return {"observations":len(values),"mean_pixels":float(data.mean()),"rms_pixels":float(np.sqrt(np.square(data).mean())),"p95_pixels":float(np.percentile(data,95))}


def adjust(model,refine=True,threads=2):
    before=reprojection(model)
    options=colmap.BundleAdjustmentOptions({"refine_focal_length":refine,"refine_principal_point":False,
        "refine_extra_params":refine,"print_summary":False,"backend":colmap.BundleAdjustmentBackend.CERES,
        "ceres":{"use_gpu":False,"solver_options":{"num_threads":threads,"max_num_iterations":60,"max_solver_time_in_seconds":90}}})
    config=colmap.BundleAdjustmentConfig()
    for ident in model.reg_image_ids():config.add_image(ident)
    config.fix_gauge(colmap.BundleAdjustmentGauge.TWO_CAMS_FROM_WORLD)
    summary=colmap.create_default_bundle_adjuster(options,config,model).solve()
    raw=summary.todict();ceres=raw["ceres_summary"]
    initial,final=float(ceres["initial_cost"]),float(ceres["final_cost"])
    if (not math.isfinite(initial) or not math.isfinite(final) or final<0 or final>initial+max(1e-8,abs(initial)*1e-10)
            or summary.termination_type not in (colmap.BundleAdjustmentTerminationType.CONVERGENCE,colmap.BundleAdjustmentTerminationType.NO_CONVERGENCE)):
        raise RuntimeError("Actual Ceres bundle adjustment failed or increased the objective: "+summary.brief_report())
    return {"backend":"Ceres CPU","report":summary.brief_report(),"termination":summary.termination_type.name,
        "initial_cost":initial,"final_cost":final,"num_residuals":int(raw["num_residuals"]),
        "successful_steps":int(ceres["num_successful_steps"]),"seconds":float(ceres["total_time_in_seconds"]),
        "reprojection_before":before,"reprojection_after":reprojection(model),"gauge":"TWO_CAMS_FROM_WORLD"}


def install_probe():
    """Actual CPU feature extraction and Ceres evaluation, separate from SfM QA."""
    rng=np.random.default_rng(4352)
    pixels=rng.integers(0,256,(192,256),dtype=np.uint8)
    extractor=colmap.FeatureExtractor.create(colmap.FeatureExtractionOptions({"num_threads":1,"use_gpu":False,
        "sift":{"max_num_features":512}}),colmap.Device.cpu)
    keypoints,descriptors=extractor.extract_from_uint8_array(pixels)
    model=colmap.synthesize_dataset(colmap.SyntheticDatasetOptions({"num_rigs":1,"num_cameras_per_rig":1,
        "num_frames_per_rig":4,"num_points3D":50,"camera_model_id":colmap.CameraModelId.PINHOLE,
        "camera_params":[650.,650.,320.,240.],"camera_width":640,"camera_height":480,
        "num_points2D_without_point3D":0}))
    for point in model.points3D.values():point.xyz=point.xyz+rng.normal(0,.02,3)
    solved=adjust(model,False,1)
    checks={"actual_cpu_sift":len(keypoints)>20,"actual_ceres_loss_reduction":solved["initial_cost"]>1e-6 and solved["final_cost"]<solved["initial_cost"]*.01,
            "actual_ceres_pixel_residual":solved["reprojection_after"]["rms_pixels"]<.001}
    return {"available":all(checks.values()),"versions":versions(),"cuda_compiled":bool(colmap.has_cuda),"checks":checks,
            "features":len(keypoints),"bundle_adjustment":solved,
            "scope":"Readiness: actual CPU SIFT on generated pixels and Ceres on perturbed upstream synthetic geometry; complete image-to-SfM acceptance is separate."}


def normalize(request,work):
    directory=work/"images";directory.mkdir();records=[];dimensions=None;pixels=0
    for item in request["inputs"]:
        with Image.open(item["path"]) as source:
            if source.format not in {"PNG","JPEG"}:raise ValueError("Photographs must decode as actual PNG or JPEG images.")
            if getattr(source,"n_frames",1)!=1:raise ValueError("Animated images are not reconstruction photographs.")
            if source.width*source.height>16*1024*1024:raise ValueError("A photograph exceeds the 16-megapixel decoded size bound.")
            orientation=source.getexif().get(274,1);image=ImageOps.exif_transpose(source)
            if "A" in image.getbands() and image.getchannel("A").getextrema()!=(255,255):raise ValueError("Reconstruction photographs must be opaque; alpha is not silently discarded.")
            if image.mode=="P" and "transparency" in image.info and image.convert("RGBA").getchannel("A").getextrema()!=(255,255):raise ValueError("Transparent palette photographs require explicit opaque preparation.")
            if image.size!=(item["width"],item["height"]):raise ValueError("Normalized photograph dimensions differ from its admitted image identity.")
            if dimensions is not None and image.size!=dimensions:raise ValueError("This shared-camera workflow requires the same normalized dimensions for every photograph.")
            dimensions=image.size;pixels+=image.width*image.height
            if pixels>128*1024*1024:raise ValueError("The decoded photographs exceed the aggregate 128-megapixel bound.")
            path=directory/(item["member_stem"]+".png");image.convert("RGB").save(path)
            records.append({"asset_id":item["asset_id"],"name":item["name"],"normalized_name":path.name,
                "source_sha256":item["sha256"],"normalized_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                "exif_orientation":orientation,"width":image.width,"height":image.height})
    return directory,records


def database_statistics(path,records):
    names={r["normalized_name"]:r["asset_id"] for r in records}
    with sqlite3.connect(path) as connection:
        feature_counts={names[name]:int(rows) for name,rows in connection.execute("SELECT images.name,keypoints.rows FROM images JOIN keypoints USING(image_id)")}
        matches=list(connection.execute("SELECT rows FROM matches"));verified=list(connection.execute("SELECT rows FROM two_view_geometries WHERE rows>0"))
    return {"features_per_asset":feature_counts,"features":sum(feature_counts.values()),"matched_pairs":len(matches),
            "raw_matches":sum(int(v[0]) for v in matches),"verified_pairs":len(verified),"verified_matches":sum(int(v[0]) for v in verified)}


def undistorted_bundle(model,records,directory,output,max_image_size):
    by_name={r["normalized_name"]:r for r in records};cameras=[];tiles=[];manifest=[]
    options=colmap.UndistortCameraOptions({"max_image_size":max_image_size,"blank_pixels":0.})
    with zipfile.ZipFile(output/"undistorted-images.zip","w",compression=zipfile.ZIP_STORED,allowZip64=False) as archive:
        for ident in sorted(model.reg_image_ids()):
            image=model.images[ident];record=by_name[image.name];bitmap=colmap.Bitmap.read(directory/image.name,True)
            if bitmap is None:raise ValueError("A normalized source photograph could not be read by COLMAP.")
            corrected,camera=colmap.undistort_image(options,bitmap,image.camera)
            array=corrected.to_array();member=image.name;path=output.parent/("corrected-"+member)
            Image.fromarray(array).save(path);data=path.read_bytes();archive.write(path,member);path.unlink()
            pose=image.cam_from_world();item={"image_id":ident,"camera_id":image.camera_id,"asset_id":record["asset_id"],"name":record["name"],
                "normalized_name":image.name,"source_model":image.camera.model_name,"source_params":image.camera.params.tolist(),
                "rotation":pose.rotation.matrix().tolist(),"translation":pose.translation.tolist(),"center":image.projection_center().tolist(),
                "undistorted":{"model":camera.model_name,"width":camera.width,"height":camera.height,"params":camera.params.tolist(),
                    "member":member,"sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data)}}
            if camera.model_name!="PINHOLE" or len(camera.params)!=4:raise ValueError("Official undistortion did not return a supported PINHOLE calibration.")
            cameras.append(item);manifest.append(item)
            if len(tiles)<12:
                tile=Image.fromarray(array);tile.thumbnail((320,240));canvas=Image.new("RGB",(320,264),(18,25,34));canvas.paste(tile,((320-tile.width)//2,0))
                ImageDraw.Draw(canvas).text((8,244),f"Camera {ident} · {record['asset_id'][:12]}",fill=(220,230,245));tiles.append(canvas)
        archive.writestr("manifest.json",encoded({"version":1,"type":"colmap-official-undistorted-reference-images","cameras":manifest,
            "scope":"Pixels and camera intrinsics are the output of pycolmap.undistort_image. Original photographs and original distorted COLMAP observations are preserved separately."}))
    columns=min(4,len(tiles));preview=Image.new("RGB",(columns*320,math.ceil(len(tiles)/columns)*264),(18,25,34))
    for index,tile in enumerate(tiles):preview.paste(tile,((index%columns)*320,(index//columns)*264))
    preview.save(output/"preview.png")
    return cameras


def reconstruct(request):
    started=time.monotonic();settings=request["settings"];output=Path(request["output_dir"]);work=Path(request["work_dir"]);work.mkdir()
    progress(request,.04,"Normalize immutable photographs")
    images,records=normalize(request,work);database=work/"database.db";models=work/"models";models.mkdir()
    reader={"camera_model":settings["camera_model"],"default_focal_length_factor":1.2}
    if settings["camera_params"] is not None:reader["camera_params"]=",".join(map(str,settings["camera_params"]))
    progress(request,.12,"Extract CPU SIFT features")
    colmap.extract_features(database,images,image_names=[r["normalized_name"] for r in records],camera_mode=colmap.CameraMode.SINGLE,
        reader_options=reader,extraction_options={"max_image_size":settings["max_image_size"],"num_threads":settings["threads"],"use_gpu":False,
            "sift":{"max_num_features":settings["max_features"]}},device=colmap.Device.cpu)
    progress(request,.3,"Match features and verify two-view geometry")
    matching={"num_threads":settings["threads"],"use_gpu":False,"max_num_matches":32768}
    if settings["matching"]=="exhaustive":colmap.match_exhaustive(database,matching_options=matching,device=colmap.Device.cpu)
    else:colmap.match_sequential(database,matching_options=matching,pairing_options={"overlap":min(10,len(records)-1),"loop_detection":False},device=colmap.Device.cpu)
    statistics=database_statistics(database,records)
    if statistics["verified_pairs"]<2:raise ValueError("Not enough verified image overlap for an actual reconstruction. No camera pose or geometry was fabricated.")
    refine=settings["refine_intrinsics"]
    options=colmap.IncrementalPipelineOptions({"num_threads":settings["threads"],"random_seed":settings["seed"],"multiple_models":False,"min_model_size":3,
        "ba_refine_focal_length":refine,"ba_refine_principal_point":False,"ba_refine_extra_params":refine,"ba_use_gpu":False,
        "ba_local_max_num_iterations":30,"ba_global_max_num_iterations":50,"max_runtime_seconds":720,
        "mapper":{"num_threads":settings["threads"],"random_seed":settings["seed"],"abs_pose_refine_focal_length":refine,"abs_pose_refine_extra_params":refine}})
    progress(request,.5,"Incremental structure from motion")
    maps=colmap.incremental_mapping(database,images,models,options=options)
    if not maps:raise ValueError("COLMAP could not initialize a measured reconstruction from the selected photographs.")
    model=max(maps.values(),key=lambda item:(item.num_reg_images(),item.num_points3D()))
    registered={model.images[i].name for i in model.reg_image_ids()};unregistered=[r["asset_id"] for r in records if r["normalized_name"] not in registered]
    if model.num_reg_images()<3 or model.num_points3D()<10:raise ValueError("COLMAP did not recover at least three registered cameras and ten measured points.")
    if settings["require_all_images"] and unregistered:raise ValueError(f"COLMAP registered {model.num_reg_images()} of {len(records)} photographs. Review capture overlap or explicitly allow a partial reconstruction.")
    if model.num_points3D()>250000:raise ValueError("The reconstructed point set exceeds the 250,000-point publication bound.")
    progress(request,.78,"Ceres global bundle adjustment")
    adjustment=adjust(model,refine,settings["threads"])
    model.write_text(output);model.export_PLY(output/"sparse.ply")
    with closing(sqlite3.connect(database)) as source,closing(sqlite3.connect(output/"database.db")) as destination:
        source.backup(destination)
        # A scientific export must stand alone. Persisting WAL mode would
        # allow ordinary future readers to create unowned sidecar artifacts.
        if destination.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower()!="delete":
            raise RuntimeError("The feature database could not be exported without journal sidecars.")
        destination.commit()
    progress(request,.88,"Official calibrated image undistortion")
    cameras=undistorted_bundle(model,records,images,output,settings["max_image_size"])
    sorted_points=sorted(model.points3D.items(),key=lambda item:(-item[1].track.length(),item[1].error,item[0]))
    marker_points=[{"id":int(ident),"xyz":point.xyz.tolist(),"color":point.color.tolist(),"track_length":point.track.length()}
                   for ident,point in sorted_points[:settings["marker_limit"]]]
    statistics.update(input_images=len(records),registered_images=model.num_reg_images(),points3D=model.num_points3D(),
                      observations=model.compute_num_observations(),mean_track_length=model.compute_mean_track_length(),
                      reprojection=adjustment["reprojection_after"],marker_points=len(marker_points),elapsed_seconds=time.monotonic()-started)
    metadata={"version":1,"engine":"COLMAP","cameras":cameras,"marker_points":marker_points,"statistics":statistics,
              "bundle_adjustment":adjustment,"unregistered_asset_ids":unregistered,
              "normalization":{"photos":records,"pixel_origin":"COLMAP pixel centers start at (0.5,0.5)",
                  "feature_pixels":"EXIF orientation applied, decoded opaque RGB8 PNG; original admitted bytes unchanged",
                  "intrinsics":"One shared camera; initial numeric parameters are user-specified or focal=1.2*max(width,height), not inferred from discarded EXIF",
                  "world":"Unscaled COLMAP reconstruction coordinates; scene scale/up-axis are explicit proposal settings"}}
    (output/"reconstruction.json").write_bytes(encoded(metadata));progress(request,.97,"Verify immutable reconstruction artifacts")
    return {"engine":{"name":"COLMAP","versions":versions(),"device":"CPU","cuda_compiled":bool(colmap.has_cuda)},
            "scope":{"sparse":"Actual SIFT extraction, descriptor matching, two-view verification, incremental reconstruction and Ceres bundle adjustment",
                     "dense":"Not implemented: standard managed wheels lack CUDA PatchMatch; no dense reconstruction or watertight mesh is claimed",
                     "components":"One largest connected reconstruction; unregistered photographs are explicit and rejected unless partial output is authorized",
                     "camera":"Original lens models retained in COLMAP artifacts; editable scene cameras use official undistorted pixels and PINHOLE intrinsics",
                     "markers":"At most the requested number of sparse points become monochrome tetrahedral editing markers; full measured colored points remain in PLY/COLMAP outputs",
                     "scale":"SfM absolute metric scale and world up are not inferred"}}


def main():
    try:
        raw=sys.stdin.buffer.read(4*1024*1024+1)
        if len(raw)>4*1024*1024:raise ValueError("Reconstruction worker request is too large.")
        request=json.loads(raw);versions()
        if request.get("command")=="doctor":result={"available":True,"versions":versions(),"cuda_compiled":bool(colmap.has_cuda)}
        elif request.get("command")=="install_probe":result=install_probe()
        elif request.get("command")=="reconstruct":result=reconstruct(request)
        else:raise ValueError("Unknown fixed reconstruction worker command.")
        sys.stdout.buffer.write(encoded(result));return 0
    except Exception as exc:
        sys.stdout.buffer.write(encoded({"available":False,"error":str(exc)}));return 1


if __name__=="__main__":raise SystemExit(main())
