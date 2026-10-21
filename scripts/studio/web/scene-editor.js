/* Offline scene authoring. Z is up; rotations are XYZ Euler degrees.
 * The WebGL viewport is an interactive approximation. Blender renders the
 * saved recipe; no viewport screenshot is presented as a final render. */
(() => {
  'use strict';
  const copy = value => JSON.parse(JSON.stringify(value));
  const clamp = (v,a,b) => Math.max(a,Math.min(b,v));
  const esc = value => String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const uid = () => 's'+(globalThis.crypto?.randomUUID?.().replaceAll('-','') || Date.now().toString(36)+Math.random().toString(36).slice(2));
  const deg = Math.PI/180;
  const sub = (a,b) => a.map((v,i)=>v-b[i]);
  const add = (a,b) => a.map((v,i)=>v+b[i]);
  const mul = (a,s) => a.map(v=>v*s);
  const dot = (a,b) => a.reduce((s,v,i)=>s+v*b[i],0);
  const cross = (a,b) => [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  const norm = a => mul(a,1/(Math.hypot(...a)||1));
  const color = hex => [1,3,5].map(i=>{const c=parseInt(hex.slice(i,i+2),16)/255;return c<=.04045?c/12.92:((c+.055)/1.055)**2.4;});
  const identity = () => [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
  function matrixProduct(a,b) {const out=new Array(16).fill(0);for(let c=0;c<4;c++)for(let r=0;r<4;r++)for(let k=0;k<4;k++)out[c*4+r]+=a[k*4+r]*b[c*4+k];return out;}
  function cameraBasis(eye,target,roll=0) {const z=norm(sub(eye,target));let up=[0,0,1];if(Math.abs(dot(z,up))>.999)up=[0,1,0];const right=norm(cross(up,z)),baseUp=cross(z,right),c=Math.cos(roll*deg),s=Math.sin(roll*deg);return {right:add(mul(right,c),mul(baseUp,s)),up:add(mul(baseUp,c),mul(right,-s)),forward:mul(z,-1),backward:z};}
  function lookAt(eye,target,roll=0,basis=null) {const {right:x,up:y,backward:z}=basis||cameraBasis(eye,target,roll);return [x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,eye),-dot(y,eye),-dot(z,eye),1];}
  function perspective(fov,aspect,near=.05,far=5000,shiftX=0,shiftY=0,focalRatio=1) {const f=1/Math.tan(fov*deg/2),nf=1/(near-far);return [f/aspect*focalRatio,0,0,0,0,f,0,0,-2*shiftX,-2*shiftY,(far+near)*nf,-1,0,0,2*far*near*nf,0];}
  function cameraProjection(camera,width,height) {return matrixProduct(perspective(camera.fov,width/height,.05,5000,camera.shift_x||0,camera.shift_y||0,camera.focal_ratio??1),lookAt(camera.position,camera.target,camera.roll||0,camera.basis));}
  function rotation(v) {const [x,y,z]=v.map(a=>a*deg),cx=Math.cos(x),sx=Math.sin(x),cy=Math.cos(y),sy=Math.sin(y),cz=Math.cos(z),sz=Math.sin(z);return [cz*cy,sz*cy,-sy,0,cz*sy*sx-sz*cx,sz*sy*sx+cz*cx,cy*sx,0,cz*sy*cx+sz*sx,sz*sy*cx-cz*sx,cy*cx,0,0,0,0,1];}
  function modelMatrix(pose) {const out=rotation(pose.rotation);for(let i=0;i<3;i++)for(let j=0;j<3;j++)out[i*4+j]*=pose.scale[i];for(let i=0;i<3;i++)out[12+i]=pose.position[i];return out;}
  function normalMatrix(pose) {const r=rotation(pose.rotation);return [r[0]/pose.scale[0],r[1]/pose.scale[0],r[2]/pose.scale[0],r[4]/pose.scale[1],r[5]/pose.scale[1],r[6]/pose.scale[1],r[8]/pose.scale[2],r[9]/pose.scale[2],r[10]/pose.scale[2]];}
  function transform(m,v,w=1) {return [0,1,2,3].map(r=>m[r]*v[0]+m[4+r]*v[1]+m[8+r]*v[2]+m[12+r]*w);}
  const CAMERA_DEFAULTS={position:[7,-9,6],target:[0,0,1],fov:45,orientation_mode:'transport',sensor_height_mm:24,roll:0,shift_x:0,shift_y:0,focal_ratio:1,dof_enabled:false,focus_distance:10,f_stop:5.6,aperture_blades:0,aperture_rotation:0,aperture_ratio:1};
  const RENDER_DEFAULTS={max_bounces:12,diffuse_bounces:4,glossy_bounces:4,transmission_bounces:12,transparent_max_bounces:8,use_denoising:true,seed:0};
  const MATERIAL_DEFAULTS={color:'#d8a85f',roughness:.45,metallic:0,transmission:0,ior:1.5,emission_color:'#ffffff',emission_strength:0};
  const focalLength=(camera,pose=camera)=>camera.sensor_height_mm/(2*Math.tan(pose.fov*deg/2));
  function defaultScene(options={}) {return {version:1,width:options.width||1280,height:options.height||720,frame_end:options.frame_end||96,samples:32,render:copy(RENDER_DEFAULTS),world:{color:'#263142',strength:.35,transparent:false},output:{linear_exr:false,passes:[]},camera:copy(CAMERA_DEFAULTS),objects:[],lights:[{id:'key',name:'Key light',type:'area',position:[3,-4,7],target:[0,0,0],color:'#fff0dd',power:1100,size:5},{id:'fill',name:'Fill light',type:'area',position:[-4,1,4],target:[0,0,0],color:'#b8d7ff',power:650,size:4}]};}
  const POSE_FIELDS = {object:['position','rotation','scale'],camera:['position','target','fov','roll','shift_x','shift_y','focus_distance','f_stop'],light:['position','target','power','size']};
  const INTERPOLATIONS = {linear:'Linear',constant:'Hold',ease_in:'Ease in',ease_out:'Ease out',ease_in_out:'Ease in / out'};
  function easing(t,mode='linear') {if(mode==='constant')return 0;if(mode==='ease_in')return t*t;if(mode==='ease_out')return t*(2-t);if(mode==='ease_in_out')return t*t*(3-2*t);return t;}
  function aimPoses(item) {
    const base={frame:1,interpolation:'linear',position:item.position,target:item.target,roll:item.roll||0},keys=new Map([[1,base]]);
    for(const key of item.keyframes||[])keys.set(key.frame,{...base,...key});
    return [...keys.values()].sort((a,b)=>a.frame-b.frame);
  }
  function transportBasis(basis,backward) {
    let axis=cross(basis.backward,backward),s=Math.hypot(...axis),c=clamp(dot(basis.backward,backward),-1,1),right=basis.right;
    if(s>1e-12){axis=mul(axis,1/s);const tangent=cross(axis,right),along=dot(axis,right);right=right.map((v,i)=>v*c+tangent[i]*s+axis[i]*along*(1-c));}
    else if(c<0)throw Error('The interpolated aim path crosses its target. Use Hold for an intentional cut.');
    right=norm(sub(right,mul(backward,dot(right,backward))));
    return {right,up:cross(backward,right),forward:mul(backward,-1),backward};
  }
  function cameraBasisAt(item,frame) {
    const poses=aimPoses(item);let pose=poses[0],basis=cameraBasis(pose.position,pose.target);
    for(let i=1;i<poses.length;i++){
      const left=poses[i-1],right=poses[i];if(frame<=left.frame)break;
      const held=left.interpolation==='constant';
      if(frame<right.frame){const t=easing((frame-left.frame)/(right.frame-left.frame),left.interpolation);pose={position:left.position.map((v,i)=>v+(right.position[i]-v)*t),target:left.target.map((v,i)=>v+(right.target[i]-v)*t),roll:left.roll+(right.roll-left.roll)*t};}else pose=right;
      if(held){if(frame>=right.frame)basis=cameraBasis(right.position,right.target);}
      else basis=transportBasis(basis,norm(sub(pose.position,pose.target)));
      if(frame<right.frame)break;
    }
    if((item.orientation_mode||'world_up')==='world_up')return cameraBasis(pose.position,pose.target,pose.roll);
    const c=Math.cos(pose.roll*deg),s=Math.sin(pose.roll*deg);
    return {...basis,right:add(mul(basis.right,c),mul(basis.up,s)),up:add(mul(basis.up,c),mul(basis.right,-s))};
  }
  function validateAimPaths(scene) {
    for(const [item,label] of [[scene.camera,'Camera'],...scene.lights.filter(l=>l.type!=='point').map(l=>[l,'Directional light '+l.name])]){
      const poses=aimPoses(item);
      if([item,...poses].some(p=>dot(sub(p.position,p.target),sub(p.position,p.target))<.0001))throw Error(label+' position must stay at least 0.01 m from its target.');
      for(let i=1;i<poses.length;i++){
        const left=poses[i-1],right=poses[i];if(left.interpolation==='constant')continue;
        const a=sub(left.position,left.target),d=sub(sub(right.position,right.target),a),length=dot(d,d),t=length?clamp(-dot(a,d)/length,0,1):0,closest=add(a,mul(d,t));
        if(dot(closest,closest)<.0001)throw Error(`${label} aim path approaches its target within 0.01 m between frames ${left.frame} and ${right.frame}. Offset the path or use Hold for an intentional cut.`);
      }
    }
  }
  function poseAt(item,frame,kind='object') {
    const props=POSE_FIELDS[kind],base=Object.fromEntries(props.map(p=>[p,item[p]??(kind==='camera'?CAMERA_DEFAULTS[p]:undefined)])),keys=new Map([[1,{frame:1,interpolation:'linear',...base}]]);
    for(const key of item.keyframes||[])keys.set(key.frame,{...base,...key});
    const list=[...keys.values()].sort((a,b)=>a.frame-b.frame),values=key=>Object.fromEntries(props.map(p=>[p,copy(key[p])]));
    if(frame<=list[0].frame)return values(list[0]);
    for(let i=1;i<list.length;i++){
      const a=list[i-1],b=list[i];
      if(frame<b.frame){const t=easing((frame-a.frame)/(b.frame-a.frame),a.interpolation);return Object.fromEntries(props.map(p=>[p,Array.isArray(a[p])?a[p].map((v,j)=>v+(b[p][j]-v)*t):a[p]+(b[p]-a[p])*t]));}
    }
    return values(list.at(-1));
  }
  function geometry(type) {
    const vertices=[],normals=[];
    const triangle=(a,b,c,na,nb,nc)=>{vertices.push(...a,...b,...c);const n=na||norm(cross(sub(b,a),sub(c,a)));normals.push(...n,...(nb||n),...(nc||n));};
    const quad=(a,b,c,d,n)=>{triangle(a,b,c,n);triangle(a,c,d,n);};
    if(type==='cube'){
      quad([-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1],[0,0,1]);quad([-1,1,-1],[1,1,-1],[1,-1,-1],[-1,-1,-1],[0,0,-1]);
      quad([1,-1,-1],[1,1,-1],[1,1,1],[1,-1,1],[1,0,0]);quad([-1,1,-1],[-1,-1,-1],[-1,-1,1],[-1,1,1],[-1,0,0]);
      quad([1,1,-1],[-1,1,-1],[-1,1,1],[1,1,1],[0,1,0]);quad([-1,-1,-1],[1,-1,-1],[1,-1,1],[-1,-1,1],[0,-1,0]);
    } else if(type==='plane')quad([-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0],[0,0,1]);
    else if(type==='sphere'){
      const p=(lat,lon)=>[Math.sin(lat)*Math.cos(lon),Math.sin(lat)*Math.sin(lon),Math.cos(lat)];
      for(let i=0;i<16;i++)for(let j=0;j<32;j++){const a=p(i*Math.PI/16,j*2*Math.PI/32),b=p((i+1)*Math.PI/16,j*2*Math.PI/32),c=p((i+1)*Math.PI/16,(j+1)*2*Math.PI/32),d=p(i*Math.PI/16,(j+1)*2*Math.PI/32);triangle(a,b,c,a,b,c);triangle(a,c,d,a,c,d);}
    }else if(type==='cylinder')for(let j=0;j<32;j++){const a=j*2*Math.PI/32,b=(j+1)*2*Math.PI/32,pa=[Math.cos(a),Math.sin(a)],pb=[Math.cos(b),Math.sin(b)],n=norm([pa[0]+pb[0],pa[1]+pb[1],0]);quad([...pa,-1],[...pb,-1],[...pb,1],[...pa,1],n);triangle([0,0,1],[...pa,1],[...pb,1],[0,0,1]);triangle([0,0,-1],[...pb,-1],[...pa,-1],[0,0,-1]);}
    return {vertices:new Float32Array(vertices),normals:new Float32Array(normals)};
  }
  function meshGeometry(mesh) {
    const vertices=new Float32Array(mesh.triangles.length*9),normals=new Float32Array(vertices.length);
    mesh.triangles.forEach((indices,face)=>{
      const points=indices.map(index=>mesh.vertices[index]),flat=norm(cross(sub(points[1],points[0]),sub(points[2],points[0])));
      points.forEach((point,corner)=>{const offset=face*9+corner*3;vertices.set(point,offset);normals.set(mesh.normals?.length?mesh.normals[mesh.normal_indices[face][corner]]:flat,offset);});
    });
    return {vertices,normals};
  }
  function geometryBounds(vertices) {
    const min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity];
    for(let i=0;i<vertices.length;i++) {const axis=i%3;min[axis]=Math.min(min[axis],vertices[i]);max[axis]=Math.max(max[axis],vertices[i]);}
    return {min,max,center:min.map((v,i)=>(v+max[i])/2),radius:Math.hypot(...sub(max,min))/2};
  }
  function intersectGeometry(data,pose,pointer,details=false) {
    // Inverse affine transform preserves the original world-ray parameter.
    // Do not normalize the scaled local ray: nonuniform scaling would then
    // make hit distances incomparable across objects.
    const r=rotation(pose.rotation),inverse=v=>[0,1,2].map(i=>(r[i*4]*v[0]+r[i*4+1]*v[1]+r[i*4+2]*v[2])/pose.scale[i]);
    const origin=inverse(sub(pointer.origin,pose.position)),direction=inverse(pointer.direction),bounds=data.bounds||geometryBounds(data.vertices);
    let near=0,far=Infinity;
    for(let i=0;i<3;i++){
      if(Math.abs(direction[i])<1e-14){if(origin[i]<bounds.min[i]||origin[i]>bounds.max[i])return null;continue;}
      let a=(bounds.min[i]-origin[i])/direction[i],b=(bounds.max[i]-origin[i])/direction[i];if(a>b)[a,b]=[b,a];near=Math.max(near,a);far=Math.min(far,b);if(near>far)return null;
    }
    let best=null,triangle=-1;const v=data.vertices;
    for(let i=0;i<v.length;i+=9){const a=[v[i],v[i+1],v[i+2]],b=[v[i+3],v[i+4],v[i+5]],c=[v[i+6],v[i+7],v[i+8]],edge1=sub(b,a),edge2=sub(c,a),p=cross(direction,edge2),det=dot(edge1,p);if(Math.abs(det)<1e-14)continue;
      const inverseDet=1/det,tvec=sub(origin,a),u=dot(tvec,p)*inverseDet;if(u<0||u>1)continue;const q=cross(tvec,edge1),w=dot(direction,q)*inverseDet;if(w<0||u+w>1)continue;const distance=dot(edge2,q)*inverseDet;if(distance>.05&&(best===null||distance<best)){best=distance;triangle=i/9;}
    }return best===null?null:details?{distance:best,triangle}:best;
  }
  function checkGeometryBudget(objects) {
    const records=objects.filter(item=>item.type==='mesh').map(item=>({mesh:item.mesh,...(item.modeling?{modeling:item.modeling}:{})}));
    const meshes=records.flatMap(item=>item.modeling?[item.mesh,item.modeling.evaluation.mesh]:[item.mesh]);
    const vertices=meshes.reduce((n,m)=>n+m.vertices.length,0),triangles=meshes.reduce((n,m)=>n+m.triangles.length,0);
    // Python stores integral geometry coordinates as floats (for example 1.0).
    // Reserve their extra bytes so an import/duplicate cannot make a project
    // unsaveable simply because JavaScript serializes them more compactly.
    const numericCoordinates=meshes.reduce((n,m)=>n+m.vertices.length*3+(m.normals?.length||0)*3+(m.uvs?.length||0)*2,0);
    const bytes=JSON.stringify(records).replace(/[^\x00-\x7f]/g,c=>'\\u'+c.charCodeAt(0).toString(16).padStart(4,'0')).length+numericCoordinates*3;
    if(objects.length>96||vertices>100000||triangles>200000||bytes>5*1024*1024)throw Error('This would exceed the scene geometry budget. Reduce the imported mesh or remove another mesh first.');
  }
  const vertexShader=`attribute vec3 aPosition;attribute vec3 aNormal;uniform mat4 uModel,uViewProjection;uniform mat3 uNormal;varying vec3 vPosition,vNormal;void main(){vec4 p=uModel*vec4(aPosition,1.);vPosition=p.xyz;vNormal=uNormal*aNormal;gl_Position=uViewProjection*p;gl_PointSize=7.;}`;
  const fragmentShader=`precision mediump float;varying vec3 vPosition,vNormal;uniform vec3 uColor,uEye,uWorld,uEmission;uniform float uRoughness,uMetallic,uTransmission,uIor,uUnlit;uniform int uLightCount;uniform vec3 uLightPosition[16],uLightColor[16],uLightParameters[16];void main(){if(uUnlit>.5){gl_FragColor=vec4(uColor,1.);return;}vec3 n=normalize(vNormal);if(!gl_FrontFacing)n=-n;vec3 view=normalize(uEye-vPosition);float f0=pow((uIor-1.)/(uIor+1.),2.);float fresnel=f0+(1.-f0)*pow(1.-max(dot(n,view),0.),5.);vec3 result=uEmission+uColor*(uWorld+.035)*(1.-uTransmission)+uWorld*uTransmission*fresnel;for(int i=0;i<16;i++){if(i>=uLightCount)break;vec3 delta=uLightPosition[i]-vPosition;float distance2=max(1.,dot(delta,delta));vec3 l=normalize(delta);float energy=uLightParameters[i].x/(30.*distance2);if(uLightParameters[i].y>.5){l=normalize(uLightPosition[i]);energy=uLightParameters[i].x;}float diffuse=max(dot(n,l),0.);vec3 halfVector=normalize(l+view);float spec=pow(max(dot(n,halfVector),0.),mix(120.,3.,uRoughness))*(mix(.15,fresnel,uTransmission)+uMetallic*.8);result+=(uColor*diffuse*(1.-uMetallic*.6)*(1.-uTransmission)+mix(vec3(.5),uColor,uMetallic)*spec)*uLightColor[i]*energy;}result=result/(vec3(1.)+result*.3);gl_FragColor=vec4(pow(max(result,vec3(0.)),vec3(1./2.2)),1.);}`;

  function mount(host,bridge={}) {
    let scene=copy(bridge.scene||defaultScene(bridge)),selected={type:'camera',id:'camera'},frame=1;
    let playing=false,animation=0,disposed=false,gesture=null,orbitDrag=null,renderBusy=false,viewCamera=false;
    let tool='move',snap=false,autoKey=false,selectedKey=null,suppressClick=0,importBusy=false,revision=0;
    let editMode=false,elementMode='vertex',meshSelection=[],modelBusy=false;
    let renderStart=1,renderEnd=null;
    let opts={width:bridge.width,height:bridge.height,fps:bridge.fps||24,renderAvailable:!!bridge.renderAvailable};
    let orbit={target:[0,0,1],azimuth:-.9,elevation:.48,distance:13};
    const clean=()=>{
      scene.objects??=[];scene.lights??=[];scene.frame_end??=96;scene.samples??=32;
      scene.camera={...copy(CAMERA_DEFAULTS),orientation_mode:'world_up',...scene.camera};scene.render={...RENDER_DEFAULTS,...scene.render};
      scene.world={transparent:false,...scene.world};scene.output={linear_exr:false,passes:[],...scene.output};
      for(const item of scene.objects)item.material={...MATERIAL_DEFAULTS,...item.material};
      if(opts.width)scene.width=opts.width;if(opts.height)scene.height=opts.height;
      for(const item of [...scene.objects,scene.camera,...scene.lights])item.keyframes??=[];
    };clean();
    host.innerHTML=`<section class="scene-editor" aria-label="3D scene and motion authoring">
      <div class="scene-tools"><div class="scene-add"><span>Add</span>${['cube','sphere','plane','cylinder'].map(t=>`<button data-scene-add="${t}">${t[0].toUpperCase()+t.slice(1)}</button>`).join('')}<button data-scene-action="add-light">Light +</button><button data-scene-action="import-obj">Import OBJ…</button></div>
      <div class="scene-transform-tools" aria-label="Transform tool"><button data-scene-tool="move" title="Move · W">Move</button><button data-scene-tool="rotate" title="Rotate · E">Rotate</button><button data-scene-tool="scale" title="Scale · R">Scale</button><label title="Move 0.25 units · rotate 15 degrees · scale 0.1"><input class="scene-snap" type="checkbox">Snap</label></div>
      <div class="scene-model-tools" aria-label="Mesh modeling"><button data-scene-action="edit-mesh">Edit mesh</button><button data-scene-element-mode="vertex" hidden>Vertices</button><button data-scene-element-mode="face" hidden>Faces</button></div>
      <div class="scene-view-buttons"><button data-scene-action="fit">Frame selection</button><button data-scene-action="camera">Camera view</button><button data-scene-action="use-camera">Set camera from view</button><button data-scene-action="import-camera">Import camera…</button></div></div>
      <div class="scene-main"><div class="scene-viewport"><canvas tabindex="0" aria-label="3D viewport. Drag axis handles to transform. Drag empty space to orbit; Shift-drag to pan."></canvas>
      <div class="scene-gizmo-labels">${['x','y','z','free'].map(axis=>`<button data-scene-axis="${axis}" class="scene-axis scene-axis-${axis}" hidden aria-label="Transform ${axis==='free'?'in view plane':axis.toUpperCase()+' axis'}">${axis==='free'?'•':axis.toUpperCase()}</button>`).join('')}</div>
      <div class="scene-view-label"></div><div class="scene-hint">Drag handles to transform · Drag empty space to orbit · Shift-drag to pan · Scroll to zoom</div>
      <div class="scene-empty"><strong>Create your scene</strong><span>Add an object, animate its pose, light it and frame the camera.</span></div><div class="scene-message" hidden></div></div>
      <aside class="scene-properties"><div class="scene-outliner"></div><div class="scene-inspector"></div></aside></div>
      <div class="scene-motion"><div class="scene-motion-toolbar"><strong>Motion</strong><button data-scene-action="previous-key" title="Previous key">‹◆</button><button data-scene-action="next-key" title="Next key">◆›</button><button data-scene-action="keyframe">◇ Keyframe pose</button><label><input class="scene-auto-key" type="checkbox">Auto key</label><span class="scene-key-label">Select a key</span><label>To next key <select class="scene-key-interpolation" disabled>${Object.entries(INTERPOLATIONS).map(([key,label])=>`<option value="${key}">${label}</option>`).join('')}</select></label><button data-scene-action="delete-key" title="Delete selected key">Delete key</button><svg class="scene-easing-curve" viewBox="0 0 84 28" aria-label="Selected interpolation curve"><path/></svg></div><div class="scene-dope-sheet" aria-label="Scene animation dope sheet"></div></div>
      <div class="scene-footer"><button data-scene-action="play" aria-label="Play scene animation">▶</button><label>Frame <input class="scene-current-frame" type="number" min="1" value="1" step="1"></label><input class="scene-frame-slider" aria-label="Scene frame" type="range" min="1" value="1"><label>End <input class="scene-end-frame" type="number" min="1" max="7200" step="1"></label><label class="scene-samples">Samples <select><option value="4">4 · Draft</option><option value="16">16 · Preview</option><option value="32">32 · Standard</option><option value="64">64 · Fine</option><option value="128">128 · Final</option><option value="256">256 · Final+</option></select></label><button class="scene-render primary" data-scene-action="render">Render scene ↗</button></div>
      <div class="scene-footnote">Z-up · 1 unit = 1 m · Viewport is shaded preview · Depth of field, refraction and indirect lighting use the rendered scene</div>
      <dialog class="scene-import-dialog" aria-labelledby="scene-import-title"><form class="scene-import-form"><h3 id="scene-import-title">Import a polygon mesh</h3><p>Choose one OBJ and optional matching MTL files. Mesh parts retain their solid materials and UV coordinates. Texture images are not imported.</p><label>Geometry and materials<input data-scene-import-file type="file" accept=".obj,.mtl" multiple required></label><div class="scene-import-files" aria-live="polite">OBJ up to 5 MiB · MTL files together up to 1 MiB</div><div class="scene-import-options"><label>Source up axis<select data-scene-import-axis><option value="Z">Z up</option><option value="Y">Y up</option></select></label><label>Import scale<input data-scene-import-scale type="number" value="1" min="0.000001" max="10000" step="any" required></label></div><p class="scene-import-status" role="status"></p><div class="scene-import-actions"><button type="button" data-scene-import-cancel>Cancel</button><button type="submit" class="primary" data-scene-import-submit>Import mesh</button></div></form></dialog></section>`;
    const root=host.querySelector('.scene-editor'),canvas=root.querySelector('canvas'),viewport=root.querySelector('.scene-viewport');
    const inspector=root.querySelector('.scene-inspector'),outliner=root.querySelector('.scene-outliner'),message=root.querySelector('.scene-message'),dope=root.querySelector('.scene-dope-sheet');
    let gl,program,locations={},meshes={},lineBuffer,normalBuffer,resizeObserver,gizmo=null;
    const importDialog=root.querySelector('.scene-import-dialog'),importStatus=root.querySelector('.scene-import-status');
    const removers=[],listen=(el,event,fn,options)=>{el.addEventListener(event,fn,options);return ()=>el.removeEventListener(event,fn,options);};
    const capture=pointerId=>{try{root.setPointerCapture?.(pointerId);}catch(_){};};
    const report=(text,error=false)=>{message.textContent=text;message.classList.toggle('error',error);message.hidden=!text;};
    const getItem=(type,id)=>type==='object'?scene.objects.find(o=>o.id===id):type==='light'?scene.lights.find(o=>o.id===id):type==='world'?scene.world:type==='render'?scene.render:type==='output'?scene.output:scene.camera;
    const selectedItem=()=>getItem(selected.type,selected.id);
    const animated=()=>['object','camera','light'].includes(selected.type);
    const cameraPose=()=>{
      const pose={...poseAt(scene.camera,frame,'camera'),focal_ratio:scene.camera.focal_ratio};
      // A pointer drag can transiently pass through an undefined direction.
      // Keep drawing until release; publish() rejects that path atomically.
      try{pose.basis=cameraBasisAt(scene.camera,frame);}catch(_){const previous=gesture?.before?.camera||CAMERA_DEFAULTS;pose.basis=cameraBasis(previous.position,previous.target,previous.roll||0);}
      return pose;
    };
    const eye=()=>viewCamera?cameraPose().position:add(orbit.target,[Math.cos(orbit.azimuth)*Math.cos(orbit.elevation)*orbit.distance,Math.sin(orbit.azimuth)*Math.cos(orbit.elevation)*orbit.distance,Math.sin(orbit.elevation)*orbit.distance]);
    const target=()=>viewCamera?cameraPose().target:orbit.target;
    const tracks=()=>[...scene.objects.map(item=>({type:'object',id:item.id,name:item.name,item})),{type:'camera',id:'camera',name:'Render camera',item:scene.camera},...scene.lights.map(item=>({type:'light',id:item.id,name:item.name,item}))];
    function publish(before) {
      clean();
      try {validateAimPaths(scene);if(bridge.onChange?.(copy(scene))===false){if(before)scene=before;report('Finish the current project operation before editing.',true);refresh();return false;}}
      catch(error){if(before)scene=before;report(error.message||'Scene change could not be saved.',true);refresh();return false;}
      revision++;refresh();return true;
    }
    function commit(change) {const before=copy(scene);try{change();report('');return publish(before);}catch(error){scene=before;report(error.message,true);refresh();return false;}}
    function ensureKey(item,kind,at=frame) {
      item.keyframes??=[];let key=item.keyframes.find(k=>k.frame===at);
      if(!key){if(item.keyframes.length>=128)throw Error('This item already has 128 keys. Remove a key before adding another.');key={frame:at,interpolation:'linear',...poseAt(item,at,kind)};item.keyframes.push(key);item.keyframes.sort((a,b)=>a.frame-b.frame);}
      return key;
    }
    function writePose(item,kind,pose) {if(kind==='camera'&&focalLength(item,pose)<1)throw Error('The focal length must be at least 1 mm. Enlarge the sensor or narrow the field of view.');const destination=autoKey||item.keyframes.length?ensureKey(item,kind):item;for(const prop of POSE_FIELDS[kind])destination[prop]=copy(pose[prop]);}
    function updateFrameUI() {root.querySelector('.scene-current-frame').value=frame;root.querySelector('.scene-frame-slider').value=frame;dope.style.setProperty('--scene-playhead',`${(frame-1)/Math.max(1,scene.frame_end-1)*100}%`);}
    function setFrame(value) {frame=clamp(Math.round(Number(value)||1),1,scene.frame_end);updateFrameUI();if(!playing)renderInspector();draw();}
    function stop() {playing=false;cancelAnimationFrame(animation);root.querySelector('[data-scene-action="play"]').textContent='▶';}
    function play() {if(playing){stop();renderInspector();return;}if(gesture)return;playing=true;root.querySelector('[data-scene-action="play"]').textContent='Ⅱ';const start=performance.now(),initial=frame;function tick(now){if(!playing||disposed)return;setFrame(1+(initial-1+Math.floor((now-start)*opts.fps/1000))%scene.frame_end);animation=requestAnimationFrame(tick);}animation=requestAnimationFrame(tick);}
    function revealSelection() {
      inspector.scrollTop=0;
      const list=outliner.querySelector('.scene-object-list'),button=list?.querySelector('.selected');
      if(button){const bounds=list.getBoundingClientRect(),item=button.getBoundingClientRect();if(item.top<bounds.top)list.scrollTop+=item.top-bounds.top;else if(item.bottom>bounds.bottom)list.scrollTop+=item.bottom-bounds.bottom;}
    }
    function select(type,id) {const next=id||type;if(selected.type!==type||selected.id!==next){editMode=false;meshSelection=[];}selected={type,id:next};selectedKey=null;if(type!=='object')tool='move';refresh();revealSelection();}
    function addPrimitive(type) {
      if(scene.objects.length>=96){report('A scene supports at most 96 objects.',true);return;}
      commit(()=>{const item={id:uid(),name:type[0].toUpperCase()+type.slice(1)+' '+(scene.objects.length+1),type,position:[0,0,type==='plane'?0:1],rotation:[0,0,0],scale:type==='plane'?[5,5,1]:[1,1,1],material:{color:type==='plane'?'#727a88':'#d8a85f',roughness:.45,metallic:0},keyframes:[]};scene.objects.push(item);selected={type:'object',id:item.id};selectedKey=null;});
    }
    const number=(label,path,value,step=.1,min=-1000,max=1000)=>`<label>${label}<input data-scene-property="${path}" type="number" value="${Number(Number(value).toFixed(Math.max(0,Math.ceil(-Math.log10(step))+1)))}" step="${step}" min="${min}" max="${max}"></label>`;
    const checkbox=(label,path,value)=>`<label class="scene-check">${label}<input data-scene-property="${path}" type="checkbox" ${value?'checked':''}></label>`;
    const vector=(label,path,values,step=.1,min=-1000,max=1000)=>`<fieldset><legend>${label}</legend><div class="scene-vector">${['X','Y','Z'].map((name,i)=>number(name,path+'.'+i,values[i],step,min,max)).join('')}</div></fieldset>`;
    function renderOutliner() {
      const previous=outliner.querySelector('.scene-object-list')?.scrollTop||0;
      outliner.innerHTML=`<h3>Scene <span>${scene.objects.length} objects</span></h3><div class="scene-object-list">${tracks().map(t=>`<button class="${selected.type===t.type&&selected.id===t.id?'selected':''}" data-scene-select="${t.type}" data-id="${esc(t.id)}"><span>${t.type==='camera'?'▱':t.type==='light'?'☀':'◇'}</span>${esc(t.name)}<small>${t.item.keyframes.length?'◆ '+t.item.keyframes.length:t.type}</small></button>`).join('')}<button class="${selected.type==='world'?'selected':''}" data-scene-select="world"><span>◉</span>World</button><button class="${selected.type==='render'?'selected':''}" data-scene-select="render"><span>◈</span>Light paths & sampling</button><button class="${selected.type==='output'?'selected':''}" data-scene-select="output"><span>↗</span>Render outputs</button></div>`;
      outliner.querySelector('.scene-object-list').scrollTop=previous;
    }
    function meshVertices(item=selectedItem()) {
      if(!item?.modeling)return [];
      return elementMode==='vertex'?[...meshSelection]:[...new Set(meshSelection.flatMap(i=>item.modeling.faces[i]||[]))];
    }
    function meshCenter(item=selectedItem()) {
      const indices=meshVertices(item);return indices.length?[0,1,2].map(axis=>indices.reduce((n,index)=>n+item.mesh.vertices[index][axis],0)/indices.length):[0,0,0];
    }
    function modelingInspector(item) {
      if(!item.modeling)return `<fieldset class="scene-modeling-panel"><legend>Mesh modeling</legend><button data-scene-action="edit-mesh" ${typeof bridge.onModelMesh!=='function'?'disabled':''}>Convert to editable mesh</button><p class="scene-explanation">Edit vertices and faces, then add Mirror, Bevel and Subdivision. Conversion retains this object's transform and material.</p></fieldset>`;
      const m=item.modeling,count=elementMode==='vertex'?item.mesh.vertices.length:m.faces.length;
      const modNumber=(modifier,label,path,value,step,min,max)=>`<label>${label}<input data-scene-modifier="${esc(modifier.id)}" data-modifier-property="${path}" type="number" value="${value}" step="${step}" min="${min}" max="${max}"></label>`;
      const controls=m.modifiers.map((modifier,index)=>`<section class="scene-modifier" data-modifier-id="${esc(modifier.id)}"><div class="scene-modifier-heading"><label><input type="checkbox" data-scene-modifier="${esc(modifier.id)}" data-modifier-property="enabled" ${modifier.enabled?'checked':''}>${{mirror:'Mirror',bevel:'Bevel',subdivision:'Subdivision'}[modifier.type]}</label><div><button data-scene-model-action="up" data-modifier-id="${esc(modifier.id)}" ${index===0?'disabled':''} title="Move earlier">↑</button><button data-scene-model-action="down" data-modifier-id="${esc(modifier.id)}" ${index===m.modifiers.length-1?'disabled':''} title="Move later">↓</button><button data-scene-model-action="remove" data-modifier-id="${esc(modifier.id)}" title="Remove modifier">×</button></div></div>${modifier.type==='mirror'?`<label>Local axis<select data-scene-modifier="${esc(modifier.id)}" data-modifier-property="axis">${['X','Y','Z'].map(axis=>`<option ${axis===modifier.axis?'selected':''}>${axis}</option>`).join('')}</select></label><label>Bisect at origin<input type="checkbox" data-scene-modifier="${esc(modifier.id)}" data-modifier-property="bisect" ${modifier.bisect?'checked':''}></label><label>Keep opposite side<input type="checkbox" data-scene-modifier="${esc(modifier.id)}" data-modifier-property="flip" ${modifier.flip?'checked':''}></label>${modNumber(modifier,'Merge distance','merge_distance',modifier.merge_distance,.001,.000001,.1)}`:modifier.type==='bevel'?`${modNumber(modifier,'Width · local m','width',modifier.width,.01,.0001,2)}${modNumber(modifier,'Segments','segments',modifier.segments,1,1,6)}${modNumber(modifier,'Edge angle · °','angle',modifier.angle,1,0,180)}`:`<label>Method<select data-scene-modifier="${esc(modifier.id)}" data-modifier-property="method"><option value="CATMULL_CLARK" ${modifier.method==='CATMULL_CLARK'?'selected':''}>Catmull–Clark</option><option value="SIMPLE" ${modifier.method==='SIMPLE'?'selected':''}>Simple</option></select></label>${modNumber(modifier,'Levels','levels',modifier.levels,1,1,3)}`}</section>`).join('');
      return `<fieldset class="scene-modeling-panel"><legend>Editable control cage</legend><p class="scene-model-statistics">${item.mesh.vertices.length.toLocaleString()} vertices · ${m.faces.length.toLocaleString()} faces<br>${m.evaluation.mesh.triangles.length.toLocaleString()} evaluated triangles</p>${editMode?`<div class="scene-component-selection"><label>${elementMode==='vertex'?'Vertex':'Face'} index<input data-scene-element-index type="number" min="0" max="${count-1}" step="1" value="${meshSelection.at(-1)??0}"></label><button data-scene-model-action="select-all" ${count>512?'disabled':''}>Select all</button><span>${meshSelection.length} selected</span></div>${meshSelection.length?`<fieldset><legend>${meshVertices(item).length===1?'Vertex position':'Selection center'} · local m</legend><div class="scene-vector">${meshCenter(item).map((value,index)=>`<label>${'XYZ'[index]}<input data-scene-model-coordinate="${index}" type="number" min="-1000" max="1000" step=".01" value="${Number(value.toFixed(5))}"></label>`).join('')}</div></fieldset>`:''}${elementMode==='face'?`<label>Extrude · local m<input class="scene-extrusion-distance" type="number" value=".5" step=".1" min="-100" max="100"></label><div class="scene-model-actions"><button data-scene-model-action="extrude" ${meshSelection.length!==1?'disabled':''}>Extrude</button><button data-scene-model-action="subdivide" ${!meshSelection.length?'disabled':''}>Subdivide</button><button data-scene-model-action="delete-faces" ${!meshSelection.length?'disabled':''}>Delete faces</button></div>`:''}<p class="scene-explanation">Click the control cage to select. Shift-click adds or removes a selection. Drag Move handles or edit local coordinates. Topology changes rebuild normals and UVs.</p>`:`<button data-scene-action="edit-mesh">Enter Edit mesh</button>`}<p class="scene-explanation">${m.origin.kind==='import'?'Authored from '+esc(m.origin.source.name)+' · original source hash retained':m.origin.kind==='primitive'?'Authored from '+esc(m.origin.primitive):'Authored mesh · original geometry hash retained'}</p></fieldset><fieldset class="scene-modeling-panel"><legend>Nondestructive modifiers</legend><div class="scene-model-actions">${['mirror','bevel','subdivision'].map(kind=>`<button data-scene-model-action="add-${kind}" ${m.modifiers.length>=4?'disabled':''}>+ ${kind[0].toUpperCase()+kind.slice(1)}</button>`).join('')}</div>${controls}<div class="scene-model-actions"><button data-scene-model-action="refresh">Refresh geometry</button><button data-scene-model-action="apply" ${!m.modifiers.length?'disabled':''}>Apply stack</button></div><p class="scene-explanation">The shaded viewport uses the actual evaluated geometry. The saved render retains this control cage and live stack. Apply stack bakes geometry into a new editable cage.</p></fieldset>`;
    }
    function renderInspector() {
      const item=selectedItem();if(!item){selected={type:'camera',id:'camera'};return renderInspector();}
      const pose=animated()?(selected.type==='camera'?cameraPose():poseAt(item,frame,selected.type)):null;let html='';
      if(selected.type==='object')html=`<div class="scene-inspector-heading"><h3>Object</h3><div><button data-scene-action="duplicate">Duplicate</button><button data-scene-action="delete">Delete</button></div></div><label>Name<input data-scene-property="name" value="${esc(item.name)}" maxlength="120"></label>${modelingInspector(item)}${vector('Position','position',pose.position)}${vector('Rotation · degrees','rotation',pose.rotation,1,-3600,3600)}${vector('Scale','scale',pose.scale,.1,.01,100)}
        <fieldset><legend>Principled material</legend><div class="scene-material-presets">${['solid','metal','glass','emitter'].map(p=>`<button data-scene-material="${p}">${p[0].toUpperCase()+p.slice(1)}</button>`).join('')}</div>
        <label>Base color<input data-scene-property="material.color" type="color" value="${esc(item.material.color)}"></label>${number('Roughness','material.roughness',item.material.roughness,.05,0,1)}${number('Metallic','material.metallic',item.material.metallic,.05,0,1)}${number('Transmission','material.transmission',item.material.transmission,.05,0,1)}${number('Index of refraction','material.ior',item.material.ior,.01,1,4)}
        <label>Emission color<input data-scene-property="material.emission_color" type="color" value="${esc(item.material.emission_color)}"></label>${number('Emission strength','material.emission_strength',item.material.emission_strength,.1,0,1000)}<p class="scene-explanation">Glass refraction and light emitted onto other objects are calculated when rendering. Closed geometry gives glass its thickness.</p></fieldset>`;
      else if(selected.type==='camera')html=`<h3>Render camera</h3>${vector('Position · m','position',pose.position)}${vector('Look at · m','target',pose.target)}${number('Roll · degrees','roll',pose.roll,.1,-3600,3600)}
        <label>Orientation motion<select data-scene-property="orientation_mode"><option value="transport" ${item.orientation_mode==='transport'?'selected':''}>Continuous transport</option><option value="world_up" ${item.orientation_mode==='world_up'?'selected':''}>World up · legacy</option></select></label><p class="scene-explanation">Continuous transport carries the initial camera frame through poles without a roll jump. Hold starts a new orientation at the cut. Legacy world up preserves older framing and may flip near vertical directions.</p>
        <fieldset><legend>Lens & sensor</legend>${number('Focal length · mm','__focal_length_mm',focalLength(item,pose),.1,1,1000)}${number('Vertical field · °','fov',pose.fov,.1,10,100)}${number('Sensor height · mm','sensor_height_mm',item.sensor_height_mm,.1,1,100)}<p class="scene-explanation">Active gate ${(item.sensor_height_mm*scene.width/scene.height/pose.focal_ratio).toFixed(2)} × ${item.sensor_height_mm.toFixed(2)} mm. Focal length and vertical field describe the same lens; changing either updates the other.</p></fieldset>
        <fieldset><legend>Depth of field</legend>${checkbox('Enable depth of field','dof_enabled',item.dof_enabled)}${number('Focus distance · m','focus_distance',pose.focus_distance,.01,.01,10000)}<button data-scene-action="focus-aim">Focus at look-at point</button>${number('Aperture · f-stop','f_stop',pose.f_stop,.1,.1,128)}
        <label>Aperture blades<select data-scene-property="aperture_blades" data-scene-numeric>${[0,...Array.from({length:14},(_,i)=>i+3)].map(n=>`<option value="${n}" ${n===item.aperture_blades?'selected':''}>${n||'Circular'}</option>`).join('')}</select></label>${number('Blade rotation · °','aperture_rotation',item.aperture_rotation,1,-180,180)}${number('Aperture ratio','aperture_ratio',item.aperture_ratio,.05,.1,10)}<p class="scene-explanation">Keyframe focus and f-stop for focus pulls. Depth of field appears in the rendered image. F-stop controls blur without changing exposure.</p></fieldset>
        <fieldset><legend>Calibrated framing</legend>${number('Principal shift X','shift_x',pose.shift_x,.001,-2,2)}${number('Principal shift Y','shift_y',pose.shift_y,.001,-2,2)}${number('Focal ratio fx / fy','focal_ratio',item.focal_ratio,.001,.1,10)}<p class="scene-explanation">Shifts are fractions of output width and height. Focal ratio is static for the shot. Camera view uses the same roll, principal point and focal ratio as the render.</p></fieldset>`;
      else if(selected.type==='light')html=`<div class="scene-inspector-heading"><h3>Light</h3><button data-scene-action="delete">Delete</button></div><label>Name<input data-scene-property="name" value="${esc(item.name)}" maxlength="120"></label><label>Type<select data-scene-property="type">${['area','point','sun'].map(t=>`<option ${item.type===t?'selected':''} value="${t}">${t}</option>`).join('')}</select></label>${vector('Position','position',pose.position)}${item.type!=='point'?vector('Look at','target',pose.target):''}<label>Color<input type="color" data-scene-property="color" value="${esc(item.color)}"></label>${number(item.type==='sun'?'Strength':'Power · watts','power',pose.power,item.type==='sun'?.1:25,0,10000)}${number(item.type==='sun'?'Angular size · degrees':'Size · scene units','size',pose.size,.1,.01,100)}`;
      else if(selected.type==='render')html=`<h3>Light paths & sampling</h3><p class="scene-explanation">These settings control the saved Cycles render. Each ray type is also limited by the total bounce count.</p>${number('Total bounces','max_bounces',item.max_bounces,1,0,64)}${number('Diffuse bounces','diffuse_bounces',item.diffuse_bounces,1,0,64)}${number('Glossy bounces','glossy_bounces',item.glossy_bounces,1,0,64)}${number('Transmission bounces','transmission_bounces',item.transmission_bounces,1,0,64)}${number('Transparent bounces','transparent_max_bounces',item.transparent_max_bounces,1,0,64)}${checkbox('Denoise render','use_denoising',item.use_denoising)}${number('Sampling seed','seed',item.seed,1,0,2147483647)}<p class="scene-explanation">Samples are set in the render bar. More samples reduce noise; additional bounces support deeper reflection and transmission paths.</p>`;
      else if(selected.type==='output'){
        const passes={depth:'Depth · camera distance',normal:'Normal · world XYZ',vector:'Motion vectors',diffuse_color:'Diffuse color',emission:'Emission'},channels=4+(item.passes.length?4+item.passes.reduce((n,p)=>n+({depth:1,normal:3,vector:4,diffuse_color:3,emission:3}[p]||0),0):0),frames=(renderEnd??scene.frame_end)-renderStart+1,estimate=frames*scene.width*scene.height*(channels*8+8)/(1024**3);
        html=`<h3>Render outputs</h3><div class="scene-vector"><label>First frame<input data-scene-render-range="start" type="number" min="1" max="${scene.frame_end}" step="1" value="${renderStart}"></label><label>Last frame<input data-scene-render-range="end" type="number" min="${renderStart}" max="${scene.frame_end}" step="1" value="${renderEnd??scene.frame_end}"></label></div><p class="scene-explanation">${frames} frames · ${(frames/opts.fps).toFixed(2)} seconds. Rendering a range keeps the full authored animation.</p>${checkbox('Keep scene-linear EXR masters','linear_exr',item.linear_exr)}<p class="scene-explanation">32-bit float RGBA frames preserve bright values and alpha. The download includes hashes, scene data and exact frame timing. The media bin receives an opaque display movie for editing.</p><fieldset><legend>Multilayer render passes</legend>${Object.entries(passes).map(([key,label])=>`<label class="scene-check">${label}<input data-scene-render-pass="${key}" type="checkbox" ${item.passes.includes(key)?'checked':''} ${item.linear_exr?'':'disabled'}></label>`).join('')}</fieldset><p class="scene-explanation">${item.linear_exr?`Allow about ${estimate.toFixed(2)} GiB of temporary disk space plus headroom; compression depends on the image. `:''}Enable Transparent background under World to preserve the scene silhouette in the EXR alpha. Normal and vector passes retain numerical data.</p>`;
      }else html=`<h3>World</h3><label>Environment color<input type="color" data-scene-property="color" value="${esc(item.color)}"></label>${number('Environment strength','strength',item.strength,.05,0,5)}${checkbox('Transparent background','transparent',item.transparent)}<p class="scene-explanation">World lighting stays active. EXR masters preserve transparent pixels; the display movie composites them over black. Enable masters in Render outputs.</p>`;
      if(selected.type==='object'&&item.type==='mesh')html+=`<div class="scene-mesh-info"><h4>${item.modeling?'Authored control geometry':'Imported geometry'}</h4><p>${item.mesh.vertices.length.toLocaleString()} vertices · ${item.mesh.triangles.length.toLocaleString()} triangles</p><p>${item.mesh.uvs?.length?'UV coordinates retained':'No UV coordinates'} · ${item.mesh.normals?.length?'Corner normals retained':'Normals rebuilt from geometry'}</p>${item.mesh.source?`<p title="${esc(item.mesh.source.sha256)}">${esc(item.mesh.source.name)}</p>`:''}</div>`;
      if(animated())html+=`<div class="scene-keyframes"><h4>Motion <span>${item.keyframes.length} keys</span></h4><p>${item.keyframes.length?'Pose edits update a key at frame '+frame+'.':'Enable Auto key or add a pose key to begin animation.'} Drag diamonds in the motion tracks to retime. Hold keeps the preceding pose until the next key.</p></div>`;
      const selection=selected.type+':'+selected.id,scroll=inspector.dataset.selection===selection?inspector.scrollTop:0;
      inspector.innerHTML=html;inspector.dataset.selection=selection;inspector.scrollTop=scroll;
      if(modelBusy)for(const control of inspector.querySelectorAll('button,input,select'))control.disabled=true;
    }
    function renderKeyTools() {
      const selection=selectedKey,item=selection&&getItem(selection.type,selection.id),key=item?.keyframes.find(k=>k.frame===selection.frame);
      const valid=Boolean(selection&&item),mode=key?.interpolation||'linear';
      root.querySelector('.scene-key-label').textContent=valid?`Key ${selection.frame}${key?'':' · base pose'}`:'Select a key';
      const input=root.querySelector('.scene-key-interpolation');input.disabled=!valid;input.value=mode;
      root.querySelector('[data-scene-action="delete-key"]').disabled=!key;
      const samples=Array.from({length:41},(_,i)=>{const u=i/40;return `${i?'L':'M'}${2+u*80},${26-(u===1?1:easing(u,mode))*24}`;}).join(' ');
      root.querySelector('.scene-easing-curve path').setAttribute('d',samples);
      root.querySelector('.scene-easing-curve').style.opacity=valid?'1':'.25';
    }
    function renderDopeSheet() {
      const end=scene.frame_end,denominator=Math.max(1,end-1),at=f=>(f-1)/denominator*100;
      const ticks=[...new Set(Array.from({length:9},(_,i)=>1+Math.round(i*denominator/8)))];
      dope.innerHTML=`<div class="scene-dope-ruler"><span>Scene tracks</span><div>${ticks.map(t=>`<i style="left:${at(t)}%">${t}</i>`).join('')}</div></div>${tracks().map(t=>{
        const keys=[...t.item.keyframes];if(keys.length&&!keys.some(k=>k.frame===1))keys.unshift({frame:1,implicit:true});
        return `<div class="scene-dope-row ${selected.type===t.type&&selected.id===t.id?'selected':''}"><button class="scene-track-name" data-scene-select="${t.type}" data-id="${esc(t.id)}" title="${esc(t.name)}">${t.type==='camera'?'▱':t.type==='light'?'☀':'◇'} ${esc(t.name)}</button><div class="scene-key-lane" data-track-type="${t.type}" data-track-id="${esc(t.id)}">${keys.map(k=>`<button class="scene-key ${k.implicit?'implicit':''} ${selectedKey?.type===t.type&&selectedKey?.id===t.id&&selectedKey?.frame===k.frame?'selected':''}" data-scene-key="${k.frame}" data-implicit="${k.implicit?'1':'0'}" style="left:${at(k.frame)}%" title="${esc(t.name)} · frame ${k.frame} · ${INTERPOLATIONS[k.interpolation||'linear']}" aria-label="${esc(t.name)} keyframe ${k.frame}">◆</button>`).join('')}<span class="scene-motion-playhead"></span></div></div>`;
      }).join('')}`;updateFrameUI();renderKeyTools();
    }
    function refresh() {
      renderStart=clamp(renderStart,1,scene.frame_end);if(renderEnd!==null)renderEnd=clamp(renderEnd,renderStart,scene.frame_end);
      if(disposed)return;clean();frame=clamp(frame,1,scene.frame_end);if(!selectedItem())selected={type:'camera',id:'camera'};
      if(selected.type!=='object'||!selectedItem()?.modeling){editMode=false;meshSelection=[];}else meshSelection=meshSelection.filter(i=>i>=0&&i<(elementMode==='vertex'?selectedItem().mesh.vertices.length:selectedItem().modeling.faces.length));
      if(selectedKey){const item=getItem(selectedKey.type,selectedKey.id);if(!item||(selectedKey.frame!==1&&!item.keyframes.some(k=>k.frame===selectedKey.frame)))selectedKey=null;}
      renderOutliner();renderInspector();renderDopeSheet();
      root.querySelector('.scene-current-frame').max=scene.frame_end;root.querySelector('.scene-frame-slider').max=scene.frame_end;root.querySelector('.scene-end-frame').value=scene.frame_end;root.querySelector('.scene-samples select').value=String(scene.samples);
      root.querySelector('.scene-render').disabled=renderBusy||importBusy||modelBusy||!opts.renderAvailable||!scene.objects.length;
      root.querySelector('[data-scene-action="import-obj"]').disabled=importBusy||typeof bridge.onImportMesh!=='function';
      root.querySelector('[data-scene-action="import-camera"]').disabled=typeof bridge.onImportCamera!=='function';
      root.querySelector('.scene-render').title=opts.renderAvailable?'Render this authored scene into your media bin':'The Blender render engine is unavailable. Check engines to configure it.';
      root.querySelector('[data-scene-action="keyframe"]').disabled=!animated();root.querySelector('.scene-empty').hidden=!!scene.objects.length;
      root.querySelector('.scene-view-label').innerHTML=(viewCamera?'RENDER CAMERA':'PERSPECTIVE')+' <span>3D scene · '+(viewCamera?'Animated framing':'World axes')+'</span>';
      root.querySelector('[data-scene-action="camera"]').classList.toggle('active',viewCamera);
      for(const button of root.querySelectorAll('[data-scene-tool]')){button.classList.toggle('active',button.dataset.sceneTool===tool);button.disabled=modelBusy||!animated()||((selected.type!=='object'||editMode)&&button.dataset.sceneTool!=='move');}
      for(const button of root.querySelectorAll('[data-scene-action="edit-mesh"]')){button.disabled=modelBusy||selected.type!=='object'||typeof bridge.onModelMesh!=='function';if(button.closest('.scene-tools')){button.textContent=modelBusy?'Evaluating…':editMode?'Exit Edit mesh':'Edit mesh';button.classList.toggle('active',editMode);}}
      for(const button of root.querySelectorAll('[data-scene-element-mode]')){button.hidden=!editMode;button.disabled=modelBusy;button.classList.toggle('active',button.dataset.sceneElementMode===elementMode);}
      for(const button of root.querySelectorAll('[data-scene-add]'))button.disabled=modelBusy;
      root.classList.toggle('scene-edit-mode',editMode);root.classList.toggle('scene-model-busy',modelBusy);
      root.querySelector('.scene-hint').textContent=editMode?'Control cage · Click '+(elementMode==='vertex'?'vertices':'faces')+' · Shift-click to extend selection · Drag Move handles':'Drag handles to transform · Drag empty space to orbit · Shift-drag to pan · Scroll to zoom';
      pruneMeshes();draw();
    }
    function initGL() {
      gl=canvas.getContext('webgl',{antialias:true,alpha:false,preserveDrawingBuffer:true});if(!gl){report('WebGL is unavailable. Scene controls and rendering remain available.',true);return;}
      function shader(type,source){const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;}
      program=gl.createProgram();const vs=shader(gl.VERTEX_SHADER,vertexShader),fs=shader(gl.FRAGMENT_SHADER,fragmentShader);gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);gl.deleteShader(vs);gl.deleteShader(fs);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));
      for(const name of ['aPosition','aNormal'])locations[name]=gl.getAttribLocation(program,name);
      for(const name of ['uModel','uViewProjection','uNormal','uColor','uEye','uWorld','uEmission','uRoughness','uMetallic','uTransmission','uIor','uUnlit','uLightCount','uLightPosition[0]','uLightColor[0]','uLightParameters[0]'])locations[name]=gl.getUniformLocation(program,name);
      for(const type of ['cube','sphere','plane','cylinder'])meshes[type]=uploadGeometry(geometry(type));
      lineBuffer=gl.createBuffer();normalBuffer=gl.createBuffer();gl.enable(gl.DEPTH_TEST);gl.disable(gl.CULL_FACE);
    }
    function uploadGeometry(data) {const p=gl.createBuffer(),n=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,p);gl.bufferData(gl.ARRAY_BUFFER,data.vertices,gl.STATIC_DRAW);gl.bindBuffer(gl.ARRAY_BUFFER,n);gl.bufferData(gl.ARRAY_BUFFER,data.normals,gl.STATIC_DRAW);return {...data,bounds:geometryBounds(data.vertices),p,n,count:data.vertices.length/3};}
    function objectGeometry(obj) {const geometry=obj.modeling?.evaluation.mesh||obj.mesh,key=obj.type==='mesh'?'mesh:'+geometry.sha256:obj.type;if(!meshes[key]&&gl)meshes[key]=uploadGeometry(meshGeometry(geometry));return meshes[key];}
    function pruneMeshes() {if(!gl)return;const used=new Set(scene.objects.filter(obj=>obj.type==='mesh').map(obj=>'mesh:'+(obj.modeling?.evaluation.mesh||obj.mesh).sha256));for(const key of Object.keys(meshes))if(key.startsWith('mesh:')&&!used.has(key)){gl.deleteBuffer(meshes[key].p);gl.deleteBuffer(meshes[key].n);delete meshes[key];}}
    function frameSelection() {const item=selectedItem();viewCamera=false;if(selected.type==='object'){
      const pose=poseAt(item,frame),data=objectGeometry(item)||{bounds:item.type==='mesh'?geometryBounds(meshGeometry(item.mesh).vertices):geometryBounds(geometry(item.type).vertices)},bounds=data.bounds;
      orbit.target=transform(modelMatrix(pose),bounds.center).slice(0,3);orbit.distance=clamp(bounds.radius*Math.max(...pose.scale)/Math.sin(22.5*deg)*1.2,.2,2000);
    }else {orbit.target=animated()?poseAt(item,frame,selected.type).position:[0,0,1];orbit.distance=13;}}
    function bind(mesh) {gl.bindBuffer(gl.ARRAY_BUFFER,mesh.p);gl.enableVertexAttribArray(locations.aPosition);gl.vertexAttribPointer(locations.aPosition,3,gl.FLOAT,false,0,0);gl.bindBuffer(gl.ARRAY_BUFFER,mesh.n);gl.enableVertexAttribArray(locations.aNormal);gl.vertexAttribPointer(locations.aNormal,3,gl.FLOAT,false,0,0);}
    function lines(points,rgb,model=identity(),mode=gl.LINES) {if(!points.length)return;gl.bindBuffer(gl.ARRAY_BUFFER,lineBuffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(points),gl.DYNAMIC_DRAW);gl.bindBuffer(gl.ARRAY_BUFFER,normalBuffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(points.length),gl.DYNAMIC_DRAW);bind({p:lineBuffer,n:normalBuffer});gl.uniformMatrix4fv(locations.uModel,false,model);gl.uniformMatrix3fv(locations.uNormal,false,[1,0,0,0,1,0,0,0,1]);gl.uniform3fv(locations.uColor,rgb);gl.uniform1f(locations.uUnlit,1);gl.drawArrays(mode,0,points.length/3);}
    function drawEditCage() {
      const item=selectedItem();if(!editMode||selected.type!=='object'||!item?.modeling)return;
      const matrix=modelMatrix(poseAt(item,frame)),selectedVertices=new Set(meshVertices(item)),drag=gesture?.kind==='mesh'?gesture.localDelta:null;
      const vertex=index=>drag&&selectedVertices.has(index)?add(item.mesh.vertices[index],drag):item.mesh.vertices[index];
      const edges=[],selectedEdges=[],seen=new Set();
      item.modeling.faces.forEach((face,index)=>{for(let i=0;i<face.length;i++){const a=face[i],b=face[(i+1)%face.length],key=Math.min(a,b)+':'+Math.max(a,b);if(!seen.has(key)){edges.push(...vertex(a),...vertex(b));seen.add(key);}if(elementMode==='face'&&meshSelection.includes(index))selectedEdges.push(...vertex(a),...vertex(b));}});
      gl.disable(gl.DEPTH_TEST);lines(edges,[.25,.43,.56],matrix);lines(selectedEdges,[1,.68,.21],matrix);
      if(elementMode==='vertex')for(const chosen of [false,true]){
        const points=[];for(let i=0;i<item.mesh.vertices.length;i++)if(selectedVertices.has(i)===chosen)points.push(...vertex(i));
        if(points.length)lines(points,chosen?[1,.72,.26]:[.41,.68,.85],matrix,gl.POINTS);
      }
      gl.enable(gl.DEPTH_TEST);
    }
    function viewInfo() {
      const r=canvas.getBoundingClientRect();let width=r.width,height=r.height;
      if(viewCamera){const aspect=scene.width/scene.height;if(width/height>aspect)width=height*aspect;else height=width/aspect;}
      const e=eye(),look=target(),c=viewCamera?cameraPose():{position:e,target:look,fov:45,roll:0,shift_x:0,shift_y:0,focal_ratio:1};
      const {forward,right,up}=c.basis||cameraBasis(e,look,c.roll);
      return {width,height,ox:(r.width-width)/2,oy:(r.height-height)/2,eye:e,target:look,fov:c.fov,shiftX:c.shift_x,shiftY:c.shift_y,focalRatio:c.focal_ratio,forward,right,up,vp:cameraProjection(c,width,height)};
    }
    function project(point,view) {const p=transform(view.vp,point);if(p[3]<=.05)return null;return {x:view.ox+(p[0]/p[3]+1)*view.width/2,y:view.oy+(1-p[1]/p[3])*view.height/2,z:p[3]};}
    function ray(x,y,view) {const tx=(2*(x-view.ox)/view.width-1-2*view.shiftX)*Math.tan(view.fov*deg/2)*view.width/view.height/view.focalRatio,ty=(1-2*(y-view.oy)/view.height-2*view.shiftY)*Math.tan(view.fov*deg/2);return {origin:view.eye,direction:norm(add(view.forward,add(mul(view.right,tx),mul(view.up,ty))))};}
    function axisParameter(pointer,origin,axis) {const b=dot(axis,pointer.direction),w=sub(origin,pointer.origin),den=1-b*b;return Math.abs(den)<.015?null:(b*dot(pointer.direction,w)-dot(axis,w))/den;}
    function planePoint(pointer,origin,normal) {const den=dot(pointer.direction,normal);if(Math.abs(den)<.025)return null;return add(pointer.origin,mul(pointer.direction,dot(sub(origin,pointer.origin),normal)/den));}
    function cameraGuide() {const c=cameraPose(),{forward,right,up}=c.basis,center=add(c.position,mul(forward,1.3)),h=1.3*Math.tan(c.fov*deg/2),w=h*scene.width/scene.height/c.focal_ratio,corners=[[-1,-1],[1,-1],[1,1],[-1,1]].map(([x,y])=>add(add(center,mul(right,w*(x-2*c.shift_x))),mul(up,h*(y-2*c.shift_y)))),points=[];for(let i=0;i<4;i++)points.push(...c.position,...corners[i],...corners[i],...corners[(i+1)%4]);lines(points,[.37,.56,.72]);}
    function drawGizmo(view) {
      for(const button of root.querySelectorAll('[data-scene-axis]'))button.hidden=true;gizmo=null;
      const item=selectedItem();if(!animated()||!item||playing||modelBusy||(viewCamera&&selected.type==='camera'))return;
      const components=editMode?meshVertices(item):null;if(components&&!components.length)return;
      const pose=poseAt(item,frame,selected.type),localCenter=components?meshCenter(item):null,origin=components?transform(modelMatrix(pose),add(localCenter,gesture?.kind==='mesh'?gesture.localDelta||[0,0,0]:[0,0,0])).slice(0,3):pose.position,center=project(origin,view);if(!center)return;
      const length=clamp(center.z*2*Math.tan(view.fov*deg/2)*78/view.height,.03,300),axes=[[1,0,0],[0,1,0],[0,0,1]],colors=[[.95,.31,.32],[.32,.88,.48],[.35,.59,1]],paths=[];
      gl.disable(gl.DEPTH_TEST);
      axes.forEach((axis,index)=>{
        const points=[],screen=[];let label;
        if(tool==='rotate'){
          const u=axes[(index+1)%3],v=axes[(index+2)%3];
          for(let i=0;i<=64;i++){const angle=i*Math.PI/32,p=add(origin,add(mul(u,Math.cos(angle)*length),mul(v,Math.sin(angle)*length)));screen.push(project(p,view));if(i)points.push(...add(origin,add(mul(u,Math.cos(angle-Math.PI/32)*length),mul(v,Math.sin(angle-Math.PI/32)*length))),...p);}
          label=project(add(origin,add(mul(u,length*.7071),mul(v,length*.7071))),view);
        }else{const end=add(origin,mul(axis,length));points.push(...origin,...end);label=project(end,view);screen.push(center,label);}
        lines(points,colors[index]);paths.push({axis:index,screen});
        const button=root.querySelector(`[data-scene-axis="${'xyz'[index]}"]`);if(label&&Math.hypot(label.x-center.x,label.y-center.y)>12){button.hidden=false;button.style.left=label.x+'px';button.style.top=label.y+'px';button.title=`${tool[0].toUpperCase()+tool.slice(1)} ${'XYZ'[index]} · drag or arrow keys`;}
      });
      if(tool!=='rotate'){const button=root.querySelector('[data-scene-axis="free"]');button.hidden=false;button.style.left=center.x+'px';button.style.top=center.y+'px';button.title=tool==='scale'?'Uniform scale':'Move in view plane';}
      gl.enable(gl.DEPTH_TEST);gizmo={origin,pose,center,length,view,paths,...(components?{componentIndices:components}:{} )};
    }
    function draw() {
      if(!gl||disposed)return;const rect=canvas.getBoundingClientRect();if(rect.width<2||rect.height<2)return;
      const ratio=Math.min(devicePixelRatio||1,2),width=Math.round(rect.width*ratio),height=Math.round(rect.height*ratio);if(canvas.width!==width||canvas.height!==height){canvas.width=width;canvas.height=height;}
      const view=viewInfo();gl.viewport(0,0,width,height);gl.disable(gl.SCISSOR_TEST);gl.clearColor(.025,.031,.04,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
      gl.viewport(Math.round(view.ox*ratio),Math.round(view.oy*ratio),Math.round(view.width*ratio),Math.round(view.height*ratio));
      if(viewCamera){gl.enable(gl.SCISSOR_TEST);gl.scissor(Math.round(view.ox*ratio),Math.round(view.oy*ratio),Math.round(view.width*ratio),Math.round(view.height*ratio));}
      const world=color(scene.world.color),background=world.map(c=>Math.pow(c,1/2.2)*.4);gl.clearColor(...background,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.useProgram(program);
      gl.uniformMatrix4fv(locations.uViewProjection,false,view.vp);gl.uniform3fv(locations.uEye,view.eye);gl.uniform3fv(locations.uWorld,world.map(c=>c*scene.world.strength));
      const positions=[],colors=[],parameters=[];
      for(const light of scene.lights.slice(0,16)){const pose=poseAt(light,frame,'light');positions.push(...(light.type==='sun'?norm(sub(pose.position,pose.target)):pose.position));colors.push(...color(light.color));parameters.push(pose.power,light.type==='sun'?1:0,pose.size);}
      while(positions.length<48){positions.push(0,0,0);colors.push(0,0,0);parameters.push(0,0,0);}gl.uniform1i(locations.uLightCount,Math.min(16,scene.lights.length));gl.uniform3fv(locations['uLightPosition[0]'],positions);gl.uniform3fv(locations['uLightColor[0]'],colors);gl.uniform3fv(locations['uLightParameters[0]'],parameters);
      if(!viewCamera){const grid=[];for(let i=-10;i<=10;i++)grid.push(i,-10,0,i,10,0,-10,i,0,10,i,0);lines(grid,[.16,.19,.23]);lines([-10,0,.003,10,0,.003],[.45,.18,.18]);lines([0,-10,.003,0,10,.003],[.18,.4,.27]);cameraGuide();}
      for(const obj of scene.objects){const pose=poseAt(obj,frame),mesh=objectGeometry(obj);if(!mesh)continue;bind(mesh);gl.uniformMatrix4fv(locations.uModel,false,modelMatrix(pose));gl.uniformMatrix3fv(locations.uNormal,false,normalMatrix(pose));gl.uniform3fv(locations.uColor,color(obj.material.color));gl.uniform3fv(locations.uEmission,color(obj.material.emission_color).map(c=>c*obj.material.emission_strength));gl.uniform1f(locations.uRoughness,obj.material.roughness);gl.uniform1f(locations.uMetallic,obj.material.metallic);gl.uniform1f(locations.uTransmission,obj.material.transmission);gl.uniform1f(locations.uIor,obj.material.ior);gl.uniform1f(locations.uUnlit,0);gl.drawArrays(gl.TRIANGLES,0,mesh.count);}
      if(!viewCamera)for(const light of scene.lights){const p=poseAt(light,frame,'light').position,r=.17;lines([p[0]-r,p[1],p[2],p[0]+r,p[1],p[2],p[0],p[1]-r,p[2],p[0],p[1]+r,p[2],p[0],p[1],p[2]-r,p[0],p[1],p[2]+r],[.9,.77,.42]);}
      drawEditCage();drawGizmo(view);gl.disable(gl.SCISSOR_TEST);
    }
    function pick(x,y,extend=false) {
      if(modelBusy)return;
      const view=viewInfo();if(x<view.ox||y<view.oy||x>view.ox+view.width||y>view.oy+view.height)return;let best=null;const pointer=ray(x,y,view);
      if(editMode&&selected.type==='object'&&selectedItem()?.modeling){
        const item=selectedItem(),pose=poseAt(item,frame);let chosen=null;
        if(elementMode==='vertex'){
          const matrix=modelMatrix(pose);let distance=13,depth=Infinity;
          item.mesh.vertices.forEach((point,index)=>{const p=project(transform(matrix,point).slice(0,3),view);if(!p)return;const d=Math.hypot(p.x-x,p.y-y);if(d<distance-.3||Math.abs(d-distance)<=.3&&p.z<depth){distance=d;depth=p.z;chosen=index;}});
        }else{
          const hit=intersectGeometry(meshGeometry(item.mesh),pose,pointer,true);if(hit){let triangle=0;for(let i=0;i<item.modeling.faces.length;i++){triangle+=item.modeling.faces[i].length-2;if(hit.triangle<triangle){chosen=i;break;}}}
        }
        if(chosen===null){if(!extend)meshSelection=[];}else if(extend){if(meshSelection.includes(chosen))meshSelection=meshSelection.filter(i=>i!==chosen);else if(meshSelection.length<512)meshSelection.push(chosen);}else meshSelection=[chosen];
        renderInspector();draw();return;
      }
      for(const t of tracks()){if(viewCamera&&t.type!=='object')continue;const pose=poseAt(t.item,frame,t.type);let distance=null;if(t.type==='object') {const data=objectGeometry(t.item);if(data)distance=intersectGeometry(data,pose,pointer);}else {const p=project(pose.position,view);if(p&&Math.hypot(x-p.x,y-p.y)<14)distance=Math.hypot(...sub(pose.position,pointer.origin));}if(distance!==null&&(!best||distance<best.z))best={track:t,z:distance};}
      if(best)select(best.track.type,best.track.id);
    }
    function hitGizmo(x,y) {
      if(!gizmo)return null;let found=null,best=9;
      for(const path of gizmo.paths)for(let i=1;i<path.screen.length;i++){const a=path.screen[i-1],b=path.screen[i];if(!a||!b)continue;const dx=b.x-a.x,dy=b.y-a.y,t=clamp(((x-a.x)*dx+(y-a.y)*dy)/(dx*dx+dy*dy||1),0,1),distance=Math.hypot(x-a.x-t*dx,y-a.y-t*dy);if(distance<best){best=distance;found='xyz'[path.axis];}}
      return found;
    }
    function beginTransform(event,axisName) {
      if(!gizmo||!animated())return;stop();const rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top,axis=axisName==='free'?null:[0,1,2].map(i=>i==='xyz'.indexOf(axisName)?1:0),pointer=ray(x,y,gizmo.view);
      gesture={kind:gizmo.componentIndices?'mesh':'transform',before:copy(scene),selected:{...selected},frame,axis,axisName,tool,startX:x,startY:y,...gizmo,localDelta:[0,0,0],changed:false,pointerId:event.pointerId};
      gesture.startAxis=axis?axisParameter(pointer,gizmo.origin,axis):null;gesture.startPlane=planePoint(pointer,gizmo.origin,axis||gizmo.view.forward);gesture.startAngle=Math.atan2(y-gizmo.center.y,x-gizmo.center.x);
      capture(event.pointerId);event.preventDefault();report('');
    }
    function transformMove(event) {
      const g=gesture,rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;
      if(!g.changed&&Math.hypot(x-g.startX,y-g.startY)<3)return;
      const item=getItem(g.selected.type,g.selected.id),pose=copy(g.pose),pointer=ray(x,y,g.view),index=g.axis?'xyz'.indexOf(g.axisName):-1;
      const step=g.tool==='move'?.25:g.tool==='rotate'?15:.1,quantize=v=>snap||event.ctrlKey?Math.round(v/step)*step:v;
      if(g.tool==='move'){
        if(g.axis){const parameter=axisParameter(pointer,g.origin,g.axis);let delta=parameter!==null&&g.startAxis!==null?parameter-g.startAxis:null;
          if(delta===null){const end=project(add(g.origin,mul(g.axis,g.length)),g.view),dx=(end?.x||g.center.x)-g.center.x,dy=(end?.y||g.center.y)-g.center.y;delta=((x-g.startX)*dx+(y-g.startY)*dy)/(dx*dx+dy*dy||1)*g.length;}
          pose.position[index]=clamp(quantize(g.pose.position[index]+delta),-1000,1000);
        }else{const p=planePoint(pointer,g.origin,g.view.forward);if(p&&g.startPlane)pose.position=add(g.pose.position,sub(p,g.startPlane)).map(v=>clamp(quantize(v),-1000,1000));}
      }else if(g.tool==='rotate'){
        let angle;const p=planePoint(pointer,g.origin,g.axis);if(p&&g.startPlane){const a=norm(sub(g.startPlane,g.origin)),b=norm(sub(p,g.origin));angle=Math.atan2(dot(g.axis,cross(a,b)),dot(a,b))/deg;}else angle=(Math.atan2(y-g.center.y,x-g.center.x)-g.startAngle)/deg*(dot(g.axis,g.view.forward)<0?-1:1);
        pose.rotation[index]=clamp(quantize(g.pose.rotation[index]+angle),-3600,3600);
      }else{
        if(g.axis){const p=axisParameter(pointer,g.origin,g.axis),delta=p!==null&&g.startAxis!==null?(p-g.startAxis)/g.length:((x-g.startX)-(y-g.startY))/100;pose.scale[index]=clamp(quantize(g.pose.scale[index]*Math.max(.01,1+delta)),.01,100);}
        else pose.scale=g.pose.scale.map(v=>clamp(quantize(v*Math.exp(((x-g.startX)-(y-g.startY))*.01)),.01,100));
      }
      if(g.kind==='mesh'){
        const delta=sub(pose.position,g.pose.position),r=rotation(g.pose.rotation);g.localDelta=[0,1,2].map(i=>(r[i*4]*delta[0]+r[i*4+1]*delta[1]+r[i*4+2]*delta[2])/g.pose.scale[i]);g.changed=true;draw();return;
      }
      try {writePose(item,g.selected.type,pose);g.changed=true;renderInspector();draw();}catch(error){report(error.message,true);finishGesture(false);}
    }
    function finishGesture(accept=true) {
      const g=gesture;if(!g)return;gesture=null;if(root.hasPointerCapture?.(g.pointerId))root.releasePointerCapture(g.pointerId);
      if(!accept){scene=g.before;selected=g.selected||selected;frame=g.frame??frame;selectedKey=g.originalSelectedKey||null;report('Gesture cancelled.');refresh();return;}
      if(g.kind==='mesh'){suppressClick=performance.now()+80;if(g.changed)modelOperation({type:'move_vertices',indices:g.componentIndices,delta:g.localDelta});else refresh();return;}
      if(g.changed){suppressClick=performance.now()+80;report('');publish(g.before);}else refresh();
    }
    function beginKeyDrag(event,key) {
      const lane=key.closest('.scene-key-lane'),type=lane.dataset.trackType,id=lane.dataset.trackId,at=Number(key.dataset.sceneKey);
      stop();selected={type,id};if(type!=='object')tool='move';selectedKey={type,id,frame:at};setFrame(at);
      const before=copy(scene),bounds=lane.getBoundingClientRect();
      gesture={kind:'key',before,selected:{...selected},frame:at,originalSelectedKey:{...selectedKey},originalFrame:at,oldFrame:at,type,id,startX:event.clientX,width:bounds.width,changed:false,implicit:key.dataset.implicit==='1',pointerId:event.pointerId};
      capture(event.pointerId);event.preventDefault();renderOutliner();renderKeyTools();
    }
    function moveKey(event) {
      const g=gesture;if(g.implicit||(!g.changed&&Math.abs(event.clientX-g.startX)<3))return;
      const item=getItem(g.type,g.id),next=clamp(g.originalFrame+Math.round((event.clientX-g.startX)/Math.max(1,g.width)*(scene.frame_end-1)),1,scene.frame_end);
      if(next===g.oldFrame)return;if(item.keyframes.some(k=>k.frame===next)){report('A key already exists at frame '+next+'.',true);return;}
      const key=item.keyframes.find(k=>k.frame===g.oldFrame);if(!key)return;key.frame=next;item.keyframes.sort((a,b)=>a.frame-b.frame);g.oldFrame=next;g.changed=true;frame=next;selectedKey={type:g.type,id:g.id,frame:next};report('');renderDopeSheet();renderInspector();draw();
    }
    async function modelOperation(operation) {
      if(modelBusy||disposed||selected.type!=='object'||typeof bridge.onModelMesh!=='function')return false;
      stop();const original=selectedItem(),id=original.id,startRevision=revision,identity=JSON.stringify(original);
      modelBusy=true;report('Evaluating mesh geometry…');refresh();
      try{
        const result=await bridge.onModelMesh({object:copy(original),operation});
        if(disposed)return false;
        if(revision!==startRevision||JSON.stringify(scene.objects.find(obj=>obj.id===id))!==identity)throw Error('The scene changed during mesh evaluation. Repeat the operation on the current geometry.');
        if(result?.object?.id!==id||!result.object.modeling?.evaluation?.mesh?.sha256)throw Error('The geometry engine returned no verified editable mesh.');
        const candidate=result.object,combined=scene.objects.map(obj=>obj.id===id?candidate:obj);checkGeometryBudget(combined);
        const success=commit(()=>{scene.objects=combined;selected={type:'object',id};selectedKey=null;editMode=true;tool='move';if(operation.type==='convert'){elementMode='vertex';meshSelection=[0];}else if(['delete_faces','subdivide_faces','apply_modifiers'].includes(operation.type))meshSelection=[0];});
        if(success)report(result.warnings?.length?result.warnings.join(' '):'');
        return success;
      }catch(error){if(!disposed)report(error.message||'Mesh evaluation failed.',true);return false;}
      finally{modelBusy=false;if(!disposed)refresh();}
    }
    function modelingPropertyChanged(event) {
      const input=event.target,item=selectedItem();if(modelBusy||!item?.modeling)return false;
      if(input.hasAttribute('data-scene-element-index')){const count=elementMode==='vertex'?item.mesh.vertices.length:item.modeling.faces.length;meshSelection=[clamp(Math.round(Number(input.value)||0),0,count-1)];renderInspector();draw();return true;}
      if(input.hasAttribute('data-scene-model-coordinate')){const axis=Number(input.dataset.sceneModelCoordinate),value=Number(input.value),indices=meshVertices(item);if(Number.isFinite(value)&&indices.length){const delta=[0,0,0];delta[axis]=clamp(value,-1000,1000)-meshCenter(item)[axis];modelOperation({type:'move_vertices',indices,delta});}else refresh();return true;}
      if(input.hasAttribute('data-scene-modifier')){const modifiers=copy(item.modeling.modifiers),modifier=modifiers.find(m=>m.id===input.dataset.sceneModifier);if(!modifier)return true;let value=input.type==='checkbox'?input.checked:input.type==='number'?Number(input.value):input.value;if(input.type==='number'){if(!Number.isFinite(value)){refresh();return true;}value=clamp(value,Number(input.min),Number(input.max));if(Number(input.step)===1)value=Math.round(value);}modifier[input.dataset.modifierProperty]=value;modelOperation({type:'set_modifiers',modifiers});return true;}
      return false;
    }
    function propertyChanged(event) {
      if(modelingPropertyChanged(event)||modelBusy)return;
      if(event.target.hasAttribute('data-scene-render-range')){stop();const value=Math.round(Number(event.target.value));if(Number.isFinite(value)){if(event.target.dataset.sceneRenderRange==='start')renderStart=clamp(value,1,renderEnd??scene.frame_end);else renderEnd=clamp(value,renderStart,scene.frame_end);}refresh();return;}
      if(event.target.hasAttribute('data-scene-render-pass')){if(!scene.output.linear_exr)return;const key=event.target.dataset.sceneRenderPass;commit(()=>{scene.output.passes=event.target.checked?[...new Set([...scene.output.passes,key])]:scene.output.passes.filter(p=>p!==key);});return;}
      const input=event.target.closest('[data-scene-property]');if(!input)return;stop();const item=selectedItem();if(!item)return;
      let value=input.type==='checkbox'?input.checked:input.type==='number'||input.hasAttribute('data-scene-numeric')?Number(input.value):input.value;if(input.type==='number'){if(!Number.isFinite(value)){refresh();return;}value=clamp(value,Number(input.min),Number(input.max));if(Number(input.step)===1)value=Math.round(value);}
      if(input.dataset.sceneProperty==='name'&&!value.trim()){refresh();return;}
      if(selected.type==='camera'&&input.dataset.sceneProperty==='__focal_length_mm'){
        commit(()=>{const pose=poseAt(item,frame,'camera'),fov=2*Math.atan(item.sensor_height_mm/(2*value))/deg;if(fov<10||fov>100)throw Error('This focal length gives a field of view outside the supported 10–100° range. Adjust the sensor height or choose another focal length.');pose.fov=fov;writePose(item,'camera',pose);});return;
      }
      commit(()=>{const path=input.dataset.sceneProperty.split('.'),isPose=animated()&&POSE_FIELDS[selected.type].includes(path[0]);let destination=isPose?poseAt(item,frame,selected.type):item;const pose=destination;for(let i=0;i<path.length-1;i++)destination=destination[path[i]];destination[path.at(-1)]=value;if(selected.type==='output'&&path[0]==='linear_exr'&&!value)scene.output.passes=[];if(isPose)writePose(item,selected.type,pose);if(selected.type==='camera'&&path[0]==='sensor_height_mm'&&[item,...item.keyframes].some(key=>focalLength(item,key)<1))throw Error('This sensor makes an authored focal length less than 1 mm. Enlarge the sensor or narrow the field of view.');});
    }
    async function importGeometry(event) {
      event.preventDefault();if(importBusy||disposed||typeof bridge.onImportMesh!=='function')return;
      const startRevision=revision,files=[...root.querySelector('[data-scene-import-file]').files],axis=root.querySelector('[data-scene-import-axis]').value,scale=Number(root.querySelector('[data-scene-import-scale]').value);
      importBusy=true;importStatus.textContent='Reading geometry…';for(const control of importDialog.querySelectorAll('button,input,select'))control.disabled=true;refresh();
      try {
        const objs=files.filter(file=>/\.obj$/i.test(file.name)),mtls=files.filter(file=>/\.mtl$/i.test(file.name));
        if(objs.length!==1||objs.length+mtls.length!==files.length)throw Error('Choose exactly one OBJ and optional MTL files.');
        if(objs[0].size>5*1024*1024||mtls.length>8||mtls.reduce((n,f)=>n+f.size,0)>1024*1024)throw Error('OBJ limit: 5 MiB. At most eight MTL files totaling 1 MiB.');
        if(!Number.isFinite(scale)||scale<.000001||scale>10000)throw Error('Import scale must be between 0.000001 and 10000.');
        const decoder=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}),read=async file=>decoder.decode(await file.arrayBuffer()),materials=Object.create(null);
        const obj=await read(objs[0]);for(const file of mtls){if(Object.hasOwn(materials,file.name))throw Error('The selected MTL file names must be unique.');materials[file.name]=await read(file);}
        importStatus.textContent='Validating faces, materials and normals…';
        const result=await bridge.onImportMesh({name:objs[0].name,obj,materials,up_axis:axis,scale});
        if(disposed)return;if(revision!==startRevision)throw Error('The scene changed while importing. Import again to add the mesh to its current state.');
        if(!Array.isArray(result?.objects)||!result.objects.length)throw Error('No validated polygon geometry was returned.');
        const success=commit(()=>{const ids=new Set([...scene.objects,...scene.lights].map(item=>item.id));for(const item of result.objects){if(ids.has(item.id))item.id=uid();ids.add(item.id);}const combined=[...scene.objects,...result.objects];checkGeometryBudget(combined);scene.objects=combined;selected={type:'object',id:result.objects[0].id};selectedKey=null;});
        if(!success)throw Error(message.textContent||'The imported mesh could not be added to this project.');
        frameSelection();refresh();importDialog.close();
        report(`Imported ${result.objects.length} mesh part${result.objects.length===1?'':'s'} · ${Number(result.statistics?.triangles||0).toLocaleString()} triangles.${result.warnings?.length?' '+result.warnings.join(' '):''}`);
      }catch(error){if(!disposed)importStatus.textContent=error.message||'The mesh could not be imported.';}
      finally {importBusy=false;if(!disposed){for(const control of importDialog.querySelectorAll('button,input,select'))control.disabled=false;refresh();}}
    }
    async function action(event) {
      if(event.target.closest('.scene-import-dialog'))return;
      if(modelBusy)return;
      if(performance.now()<suppressClick)return;const addButton=event.target.closest('[data-scene-add]');if(addButton){addPrimitive(addButton.dataset.sceneAdd);return;}
      const modeButton=event.target.closest('[data-scene-element-mode]');if(modeButton){elementMode=modeButton.dataset.sceneElementMode;meshSelection=[];tool='move';refresh();return;}
      const modelButton=event.target.closest('[data-scene-model-action]');if(modelButton&&selected.type==='object'&&selectedItem()?.modeling){
        const command=modelButton.dataset.sceneModelAction,item=selectedItem(),modifiers=copy(item.modeling.modifiers),index=modifiers.findIndex(m=>m.id===modelButton.dataset.modifierId);
        if(command==='select-all'){const count=elementMode==='vertex'?item.mesh.vertices.length:item.modeling.faces.length;if(count<=512)meshSelection=Array.from({length:count},(_,i)=>i);renderInspector();draw();return;}
        if(command==='extrude'){const distance=Number(root.querySelector('.scene-extrusion-distance')?.value);if(meshSelection.length===1&&Number.isFinite(distance))await modelOperation({type:'extrude_face',face:meshSelection[0],distance});return;}
        if(command==='subdivide'||command==='delete-faces'){if(meshSelection.length)await modelOperation({type:command==='subdivide'?'subdivide_faces':'delete_faces',faces:[...meshSelection]});return;}
        if(command==='refresh'||command==='apply'){await modelOperation({type:command==='refresh'?'refresh':'apply_modifiers'});return;}
        if(command.startsWith('add-')){const type=command.slice(4);modifiers.push({id:uid(),type,enabled:true,...(type==='mirror'?{axis:'X',bisect:true,flip:false,merge_distance:.001}:type==='bevel'?{width:.1,segments:2,angle:30}:{levels:1,method:'CATMULL_CLARK'})});}
        else if(command==='remove'&&index>=0)modifiers.splice(index,1);
        else if((command==='up'||command==='down')&&index>=0){const next=index+(command==='up'?-1:1);if(next<0||next>=modifiers.length)return;[modifiers[index],modifiers[next]]=[modifiers[next],modifiers[index]];}
        else return;
        await modelOperation({type:'set_modifiers',modifiers});return;
      }
      const materialButton=event.target.closest('[data-scene-material]');if(materialButton&&selected.type==='object'){
        const preset=materialButton.dataset.sceneMaterial;commit(()=>{const item=selectedItem();item.material={...MATERIAL_DEFAULTS,color:item.material.color};if(preset==='metal')Object.assign(item.material,{metallic:1,roughness:.2});else if(preset==='glass')Object.assign(item.material,{color:'#f5faff',roughness:.05,transmission:1,ior:1.5});else if(preset==='emitter')Object.assign(item.material,{emission_color:item.material.color,emission_strength:5});});return;
      }
      const selectButton=event.target.closest('[data-scene-select]');if(selectButton){select(selectButton.dataset.sceneSelect,selectButton.dataset.id);return;}
      const toolButton=event.target.closest('[data-scene-tool]');if(toolButton){tool=toolButton.dataset.sceneTool;refresh();return;}
      const keyButton=event.target.closest('[data-scene-key]');if(keyButton){const lane=keyButton.closest('.scene-key-lane');selected={type:lane.dataset.trackType,id:lane.dataset.trackId};selectedKey={...selected,frame:Number(keyButton.dataset.sceneKey)};stop();setFrame(selectedKey.frame);refresh();return;}
      const command=event.target.closest('[data-scene-action]')?.dataset.sceneAction;if(!command)return;
      if(command==='edit-mesh'){if(selected.type!=='object')return;stop();if(!selectedItem().modeling){await modelOperation({type:'convert'});return;}editMode=!editMode;tool='move';meshSelection=editMode?[0]:[];refresh();return;}
      if(command==='play'){play();return;}
      if(command==='camera'){viewCamera=!viewCamera;refresh();return;}
      if(command==='use-camera'){const position=eye(),aim=[...target()],pose=cameraPose(),fov=viewCamera?pose.fov:45;commit(()=>{writePose(scene.camera,'camera',{...pose,position,target:aim,fov,...(viewCamera?{}:{roll:0,shift_x:0,shift_y:0})});if(!viewCamera)scene.camera.focal_ratio=1;viewCamera=true;selected={type:'camera',id:'camera'};selectedKey=null;tool='move';});return;}
      if(command==='import-camera'){if(typeof bridge.onImportCamera!=='function')return;stop();try{await bridge.onImportCamera();}catch(error){report(error.message||'Camera import could not open.',true);}return;}
      if(command==='focus-aim'){commit(()=>{const pose=cameraPose();pose.focus_distance=clamp(Math.hypot(...sub(pose.target,pose.position)),.01,10000);writePose(scene.camera,'camera',pose);});return;}
      if(command==='import-obj'){if(importBusy||typeof bridge.onImportMesh!=='function')return;stop();importStatus.textContent='';importDialog.showModal();return;}
      if(command==='fit'){frameSelection();refresh();return;}
      if(command==='delete'){if(!['object','light'].includes(selected.type))return;commit(()=>{if(selected.type==='object')scene.objects=scene.objects.filter(o=>o.id!==selected.id);else scene.lights=scene.lights.filter(o=>o.id!==selected.id);selected={type:'camera',id:'camera'};selectedKey=null;tool='move';});return;}
      if(command==='duplicate'){if(selected.type!=='object')return;commit(()=>{if(scene.objects.length>=96)throw Error('A scene supports at most 96 objects.');const item=copy(selectedItem());item.id=uid();item.name=(item.name+' copy').slice(0,120);item.position[0]=clamp(item.position[0]+2,-1000,1000);for(const key of item.keyframes)key.position[0]=clamp(key.position[0]+2,-1000,1000);checkGeometryBudget([...scene.objects,item]);scene.objects.push(item);selected={type:'object',id:item.id};selectedKey=null;});return;}
      if(command==='add-light'){commit(()=>{if(scene.lights.length>=16)throw Error('A scene supports at most 16 lights.');const light={id:uid(),name:'Light '+(scene.lights.length+1),type:'area',position:[3,-4,7],target:[0,0,0],color:'#ffffff',power:1000,size:4,keyframes:[]};scene.lights.push(light);selected={type:'light',id:light.id};selectedKey=null;tool='move';});return;}
      if(command==='keyframe'){if(!animated())return;commit(()=>{ensureKey(selectedItem(),selected.type);selectedKey={...selected,frame};});return;}
      if(command==='delete-key'){if(!selectedKey)return;commit(()=>{const item=getItem(selectedKey.type,selectedKey.id);item.keyframes=item.keyframes.filter(k=>k.frame!==selectedKey.frame);selectedKey=null;});return;}
      if(command==='previous-key'||command==='next-key'){if(!animated())return;const keys=[1,...selectedItem().keyframes.map(k=>k.frame)].sort((a,b)=>a-b),next=command==='previous-key'?[...keys].reverse().find(k=>k<frame):keys.find(k=>k>frame);if(next!==undefined){stop();setFrame(next);}return;}
      if(command==='render'){if(!opts.renderAvailable||!scene.objects.length||renderBusy||importBusy)return;renderBusy=true;stop();refresh();try{validateAimPaths(scene);await bridge.onRender?.({scene:copy(scene),frame_start:renderStart,frame_end:renderEnd??scene.frame_end});report('');}catch(error){report(error.message||'Scene render could not start.',true);}finally{renderBusy=false;refresh();}}
    }
    removers.push(listen(root,'click',action),listen(inspector,'change',propertyChanged));
    removers.push(listen(root.querySelector('.scene-import-form'),'submit',importGeometry),listen(root.querySelector('[data-scene-import-cancel]'),'click',()=>{if(!importBusy)importDialog.close();}),listen(importDialog,'cancel',event=>{if(importBusy)event.preventDefault();}));
    removers.push(listen(root.querySelector('[data-scene-import-file]'),'change',event=>{root.querySelector('.scene-import-files').textContent=[...event.target.files].map(file=>`${file.name} · ${(file.size/1024).toFixed(1)} KiB`).join('\n')||'OBJ up to 5 MiB · MTL files together up to 1 MiB';}));
    removers.push(listen(root.querySelector('.scene-key-interpolation'),'change',event=>{if(!selectedKey)return;commit(()=>{ensureKey(getItem(selectedKey.type,selectedKey.id),selectedKey.type,selectedKey.frame).interpolation=event.target.value;});}));
    removers.push(listen(root.querySelector('.scene-snap'),'change',event=>{snap=event.target.checked;}),listen(root.querySelector('.scene-auto-key'),'change',event=>{autoKey=event.target.checked;}));
    removers.push(listen(root.querySelector('.scene-current-frame'),'change',event=>{stop();setFrame(event.target.value);}),listen(root.querySelector('.scene-frame-slider'),'input',event=>{stop();setFrame(event.target.value);}));
    removers.push(listen(root.querySelector('.scene-end-frame'),'change',event=>{const end=clamp(Math.round(Number(event.target.value)||1),1,7200),last=Math.max(1,...tracks().flatMap(t=>t.item.keyframes.map(k=>k.frame)));if(end<last){report('Remove keys after frame '+end+' before shortening the scene.',true);refresh();return;}commit(()=>{scene.frame_end=end;frame=Math.min(frame,end);});}),listen(root.querySelector('.scene-samples select'),'change',event=>commit(()=>{scene.samples=Number(event.target.value);}))); 
    removers.push(listen(root,'keydown',event=>{
      if(event.key==='Escape'&&gesture){event.preventDefault();event.stopPropagation();finishGesture(false);return;}
      if(event.target.closest('.scene-import-dialog')){event.stopPropagation();return;}
      if(event.target.closest('input,select,textarea'))return;
      const handle=event.target.closest('[data-scene-axis]');
      if(handle&&['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();event.stopPropagation();if(modelBusy)return;const index='xyz'.indexOf(handle.dataset.sceneAxis),direction=['ArrowLeft','ArrowDown'].includes(event.key)?-1:1;
        if(editMode){const pose=poseAt(selectedItem(),frame),r=rotation(pose.rotation),world=[0,0,0];for(const i of index<0?[0,1,2]:[index])world[i]=.25*direction;const delta=[0,1,2].map(i=>(r[i*4]*world[0]+r[i*4+1]*world[1]+r[i*4+2]*world[2])/pose.scale[i]);modelOperation({type:'move_vertices',indices:meshVertices(),delta});return;}
        commit(()=>{const item=selectedItem(),pose=poseAt(item,frame,selected.type),property=tool==='move'?'position':tool==='rotate'?'rotation':'scale',step=tool==='rotate'?15:tool==='scale'?.1:.25,indices=index<0?[0,1,2]:[index];for(const i of indices)pose[property][i]=clamp(pose[property][i]+step*direction,tool==='scale'?.01:tool==='rotate'?-3600:-1000,tool==='scale'?100:tool==='rotate'?3600:1000);writePose(item,selected.type,pose);});return;}
      if(event.metaKey||event.ctrlKey)return;event.stopPropagation();
      if(event.code==='Space'){event.preventDefault();play();}
      else if(['w','e','r'].includes(event.key.toLowerCase())&&animated()){const requested={w:'move',e:'rotate',r:'scale'}[event.key.toLowerCase()];if((selected.type==='object'&&!editMode)||requested==='move'){tool=requested;refresh();}}
      else if(event.key==='Tab'&&selected.type==='object'){event.preventDefault();root.querySelector('[data-scene-action="edit-mesh"]')?.click();}
      else if(event.key.toLowerCase()==='i'&&animated()){event.preventDefault();commit(()=>{ensureKey(selectedItem(),selected.type);selectedKey={...selected,frame};});}
      else if(['Delete','Backspace'].includes(event.key)&&!event.target.closest('button')){event.preventDefault();if(modelBusy)return;if(editMode&&selected.type==='object'){if(elementMode==='face'&&meshSelection.length)modelOperation({type:'delete_faces',faces:[...meshSelection]});else report('Select faces in Faces mode to delete mesh geometry.',true);return;}root.querySelector(`[data-scene-action="${selectedKey?'delete-key':'delete'}"]`)?.click();}
    }));
    removers.push(listen(dope,'pointerdown',event=>{if(event.button!==0||gesture)return;const key=event.target.closest('[data-scene-key]');if(key){beginKeyDrag(event,key);return;}const lane=event.target.closest('.scene-key-lane');if(lane){stop();const rect=lane.getBoundingClientRect();setFrame(1+(event.clientX-rect.left)/rect.width*(scene.frame_end-1));selectedKey=null;renderKeyTools();}}));
    removers.push(listen(viewport,'contextmenu',event=>event.preventDefault()),listen(viewport,'pointerdown',event=>{
      if(![0,1,2].includes(event.button)||gesture)return;const axisButton=event.target.closest('[data-scene-axis]');if(event.target!==canvas&&!axisButton)return;
      event.preventDefault();canvas.focus();const rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top,axis=event.button===0&&!event.shiftKey?(axisButton?.dataset.sceneAxis||hitGizmo(x,y)):null;
      if(axis){beginTransform(event,axis);return;}stop();capture(event.pointerId);
      if(viewCamera){const pose=cameraPose(),d=sub(pose.position,pose.target);orbit={target:[...pose.target],distance:Math.hypot(...d),azimuth:Math.atan2(d[1],d[0]),elevation:Math.asin(d[2]/Math.hypot(...d))};}
      orbitDrag={x:event.clientX,y:event.clientY,initialX:event.clientX,initialY:event.clientY,pan:event.shiftKey||event.button!==0,extend:event.shiftKey,moved:false,pointerId:event.pointerId};
    }));
    removers.push(listen(root,'pointermove',event=>{
      if(gesture){if(gesture.kind==='transform'||gesture.kind==='mesh')transformMove(event);else moveKey(event);return;}if(!orbitDrag)return;
      const d=orbitDrag,dx=event.clientX-d.x,dy=event.clientY-d.y;d.moved||=Math.hypot(event.clientX-d.initialX,event.clientY-d.initialY)>3;if(!d.moved)return;viewCamera=false;
      if(d.pan){const direction=norm(sub(orbit.target,eye())),right=norm(cross(direction,[0,0,1])),up=norm(cross(right,direction)),factor=orbit.distance*.002;orbit.target=add(orbit.target,add(mul(right,-dx*factor),mul(up,dy*factor)));}else{orbit.azimuth-=dx*.008;orbit.elevation=clamp(orbit.elevation+dy*.008,-1.5,1.5);}d.x=event.clientX;d.y=event.clientY;draw();root.querySelector('.scene-view-label').innerHTML='PERSPECTIVE <span>3D scene · World axes</span>';
    }),listen(root,'pointerup',event=>{if(gesture){finishGesture(true);return;}if(!orbitDrag)return;const d=orbitDrag;orbitDrag=null;if(!d.moved){const r=canvas.getBoundingClientRect();pick(event.clientX-r.left,event.clientY-r.top,d.extend);}if(root.hasPointerCapture?.(event.pointerId))root.releasePointerCapture(event.pointerId);refresh();}),listen(root,'pointercancel',()=>{if(gesture)finishGesture(false);orbitDrag=null;}));
    removers.push(listen(canvas,'wheel',event=>{event.preventDefault();if(gesture)return;if(viewCamera){const pose=cameraPose(),d=sub(pose.position,pose.target);orbit={target:[...pose.target],distance:Math.hypot(...d),azimuth:Math.atan2(d[1],d[0]),elevation:Math.asin(d[2]/Math.hypot(...d))};viewCamera=false;}orbit.distance=clamp(orbit.distance*Math.exp(event.deltaY*.001),.2,2000);refresh();},{passive:false}));
    try{initGL();}catch(error){report('The viewport could not initialize: '+error.message,true);if(gl&&program)gl.deleteProgram(program);gl=null;}
    if(globalThis.ResizeObserver){resizeObserver=new ResizeObserver(draw);resizeObserver.observe(viewport);}else removers.push(listen(window,'resize',draw));
    refresh();
    return {
      getScene(){return copy(scene);},
      showCamera(){if(gesture)finishGesture(false);stop();selected={type:'camera',id:'camera'};selectedKey=null;viewCamera=true;tool='move';refresh();revealSelection();},
      replaceCamera(camera){stop();return commit(()=>{scene.camera={...copy(CAMERA_DEFAULTS),...copy(camera)};selected={type:'camera',id:'camera'};selectedKey=null;viewCamera=true;tool='move';});},
      setScene(next,options={}){if(gesture)finishGesture(false);stop();opts={...opts,...options};scene=copy(next||defaultScene(opts));revision++;refresh();},
      setRenderAvailable(value){opts.renderAvailable=!!value;refresh();},
      destroy(){disposed=true;stop();resizeObserver?.disconnect();for(const remove of removers)remove();if(gl){for(const mesh of Object.values(meshes)){gl.deleteBuffer(mesh.p);gl.deleteBuffer(mesh.n);}gl.deleteBuffer(lineBuffer);gl.deleteBuffer(normalBuffer);gl.deleteProgram(program);}host.replaceChildren();}
    };
  }
  window.CinematicumSceneEditor={mount,defaultScene,poseAt,easing,meshGeometry,geometryBounds,intersectGeometry,cameraBasis,cameraBasisAt,validateAimPaths,cameraProjection,focalLength};
})();
