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
  function lookAt(eye,target) {const z=norm(sub(eye,target));let up=[0,0,1];if(Math.abs(dot(z,up))>.999)up=[0,1,0];const x=norm(cross(up,z)),y=cross(z,x);return [x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,eye),-dot(y,eye),-dot(z,eye),1];}
  function perspective(fov,aspect,near=.05,far=5000) {const f=1/Math.tan(fov*deg/2),nf=1/(near-far);return [f/aspect,0,0,0,0,f,0,0,0,0,(far+near)*nf,-1,0,0,2*far*near*nf,0];}
  function rotation(v) {const [x,y,z]=v.map(a=>a*deg),cx=Math.cos(x),sx=Math.sin(x),cy=Math.cos(y),sy=Math.sin(y),cz=Math.cos(z),sz=Math.sin(z);return [cz*cy,sz*cy,-sy,0,cz*sy*sx-sz*cx,sz*sy*sx+cz*cx,cy*sx,0,cz*sy*cx+sz*sx,sz*sy*cx-cz*sx,cy*cx,0,0,0,0,1];}
  function modelMatrix(pose) {const out=rotation(pose.rotation);for(let i=0;i<3;i++)for(let j=0;j<3;j++)out[i*4+j]*=pose.scale[i];for(let i=0;i<3;i++)out[12+i]=pose.position[i];return out;}
  function normalMatrix(pose) {const r=rotation(pose.rotation);return [r[0]/pose.scale[0],r[1]/pose.scale[0],r[2]/pose.scale[0],r[4]/pose.scale[1],r[5]/pose.scale[1],r[6]/pose.scale[1],r[8]/pose.scale[2],r[9]/pose.scale[2],r[10]/pose.scale[2]];}
  function transform(m,v,w=1) {return [0,1,2,3].map(r=>m[r]*v[0]+m[4+r]*v[1]+m[8+r]*v[2]+m[12+r]*w);}
  function defaultScene(options={}) {return {version:1,width:options.width||1280,height:options.height||720,frame_end:options.frame_end||96,samples:32,world:{color:'#263142',strength:.35},camera:{position:[7,-9,6],target:[0,0,1],fov:45},objects:[],lights:[{id:'key',name:'Key light',type:'area',position:[3,-4,7],target:[0,0,0],color:'#fff0dd',power:1100,size:5},{id:'fill',name:'Fill light',type:'area',position:[-4,1,4],target:[0,0,0],color:'#b8d7ff',power:650,size:4}]};}
  const POSE_FIELDS = {object:['position','rotation','scale'],camera:['position','target','fov'],light:['position','target','power','size']};
  const INTERPOLATIONS = {linear:'Linear',constant:'Hold',ease_in:'Ease in',ease_out:'Ease out',ease_in_out:'Ease in / out'};
  function easing(t,mode='linear') {if(mode==='constant')return 0;if(mode==='ease_in')return t*t;if(mode==='ease_out')return t*(2-t);if(mode==='ease_in_out')return t*t*(3-2*t);return t;}
  function poseAt(item,frame,kind='object') {
    const props=POSE_FIELDS[kind],keys=new Map([[1,{frame:1,interpolation:'linear',...Object.fromEntries(props.map(p=>[p,item[p]]))}]]);
    for(const key of item.keyframes||[])keys.set(key.frame,key);
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
  function intersectGeometry(data,pose,pointer) {
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
    let best=null;const v=data.vertices;
    for(let i=0;i<v.length;i+=9){const a=[v[i],v[i+1],v[i+2]],b=[v[i+3],v[i+4],v[i+5]],c=[v[i+6],v[i+7],v[i+8]],edge1=sub(b,a),edge2=sub(c,a),p=cross(direction,edge2),det=dot(edge1,p);if(Math.abs(det)<1e-14)continue;
      const inverseDet=1/det,tvec=sub(origin,a),u=dot(tvec,p)*inverseDet;if(u<0||u>1)continue;const q=cross(tvec,edge1),w=dot(direction,q)*inverseDet;if(w<0||u+w>1)continue;const distance=dot(edge2,q)*inverseDet;if(distance>.05&&(best===null||distance<best))best=distance;
    }return best;
  }
  function checkGeometryBudget(objects) {
    const meshes=objects.filter(item=>item.type==='mesh').map(item=>item.mesh);
    const vertices=meshes.reduce((n,m)=>n+m.vertices.length,0),triangles=meshes.reduce((n,m)=>n+m.triangles.length,0);
    // Python stores integral geometry coordinates as floats (for example 1.0).
    // Reserve their extra bytes so an import/duplicate cannot make a project
    // unsaveable simply because JavaScript serializes them more compactly.
    const numericCoordinates=meshes.reduce((n,m)=>n+m.vertices.length*3+(m.normals?.length||0)*3+(m.uvs?.length||0)*2,0);
    const bytes=JSON.stringify(meshes).replace(/[^\x00-\x7f]/g,c=>'\\u'+c.charCodeAt(0).toString(16).padStart(4,'0')).length+numericCoordinates*3;
    if(objects.length>96||vertices>100000||triangles>200000||bytes>5*1024*1024)throw Error('This would exceed the scene geometry budget. Reduce the imported mesh or remove another mesh first.');
  }
  const vertexShader=`attribute vec3 aPosition;attribute vec3 aNormal;uniform mat4 uModel,uViewProjection;uniform mat3 uNormal;varying vec3 vPosition,vNormal;void main(){vec4 p=uModel*vec4(aPosition,1.);vPosition=p.xyz;vNormal=uNormal*aNormal;gl_Position=uViewProjection*p;}`;
  const fragmentShader=`precision mediump float;varying vec3 vPosition,vNormal;uniform vec3 uColor,uEye,uWorld;uniform float uRoughness,uMetallic,uUnlit;uniform int uLightCount;uniform vec3 uLightPosition[16],uLightColor[16],uLightParameters[16];void main(){if(uUnlit>.5){gl_FragColor=vec4(uColor,1.);return;}vec3 n=normalize(vNormal);if(!gl_FrontFacing)n=-n;vec3 view=normalize(uEye-vPosition);vec3 result=uColor*(uWorld+.035);for(int i=0;i<16;i++){if(i>=uLightCount)break;vec3 delta=uLightPosition[i]-vPosition;float distance2=max(1.,dot(delta,delta));vec3 l=normalize(delta);float energy=uLightParameters[i].x/(30.*distance2);if(uLightParameters[i].y>.5){l=normalize(uLightPosition[i]);energy=uLightParameters[i].x;}float diffuse=max(dot(n,l),0.);vec3 halfVector=normalize(l+view);float spec=pow(max(dot(n,halfVector),0.),mix(120.,3.,uRoughness))*(.15+uMetallic*.8);result+=(uColor*diffuse*(1.-uMetallic*.6)+mix(vec3(.5),uColor,uMetallic)*spec)*uLightColor[i]*energy;}result=result/(vec3(1.)+result*.3);gl_FragColor=vec4(pow(max(result,vec3(0.)),vec3(1./2.2)),1.);}`;

  function mount(host,bridge={}) {
    let scene=copy(bridge.scene||defaultScene(bridge)),selected={type:'camera',id:'camera'},frame=1;
    let playing=false,animation=0,disposed=false,gesture=null,orbitDrag=null,renderBusy=false,viewCamera=false;
    let tool='move',snap=false,autoKey=false,selectedKey=null,suppressClick=0,importBusy=false,revision=0;
    let opts={width:bridge.width,height:bridge.height,fps:bridge.fps||24,renderAvailable:!!bridge.renderAvailable};
    let orbit={target:[0,0,1],azimuth:-.9,elevation:.48,distance:13};
    const clean=()=>{
      scene.objects??=[];scene.lights??=[];scene.frame_end??=96;scene.samples??=32;
      if(opts.width)scene.width=opts.width;if(opts.height)scene.height=opts.height;
      for(const item of [...scene.objects,scene.camera,...scene.lights])item.keyframes??=[];
    };clean();
    host.innerHTML=`<section class="scene-editor" aria-label="3D scene and motion authoring">
      <div class="scene-tools"><div class="scene-add"><span>Add</span>${['cube','sphere','plane','cylinder'].map(t=>`<button data-scene-add="${t}">${t[0].toUpperCase()+t.slice(1)}</button>`).join('')}<button data-scene-action="add-light">Light +</button><button data-scene-action="import-obj">Import OBJ…</button></div>
      <div class="scene-transform-tools" aria-label="Transform tool"><button data-scene-tool="move" title="Move · W">Move</button><button data-scene-tool="rotate" title="Rotate · E">Rotate</button><button data-scene-tool="scale" title="Scale · R">Scale</button><label title="Move 0.25 units · rotate 15 degrees · scale 0.1"><input class="scene-snap" type="checkbox">Snap</label></div>
      <div class="scene-view-buttons"><button data-scene-action="fit">Frame selection</button><button data-scene-action="camera">Camera view</button><button data-scene-action="use-camera">Set camera from view</button></div></div>
      <div class="scene-main"><div class="scene-viewport"><canvas tabindex="0" aria-label="3D viewport. Drag axis handles to transform. Drag empty space to orbit; Shift-drag to pan."></canvas>
      <div class="scene-gizmo-labels">${['x','y','z','free'].map(axis=>`<button data-scene-axis="${axis}" class="scene-axis scene-axis-${axis}" hidden aria-label="Transform ${axis==='free'?'in view plane':axis.toUpperCase()+' axis'}">${axis==='free'?'•':axis.toUpperCase()}</button>`).join('')}</div>
      <div class="scene-view-label"></div><div class="scene-hint">Drag handles to transform · Drag empty space to orbit · Shift-drag to pan · Scroll to zoom</div>
      <div class="scene-empty"><strong>Create your scene</strong><span>Add an object, animate its pose, light it and frame the camera.</span></div><div class="scene-message" hidden></div></div>
      <aside class="scene-properties"><div class="scene-outliner"></div><div class="scene-inspector"></div></aside></div>
      <div class="scene-motion"><div class="scene-motion-toolbar"><strong>Motion</strong><button data-scene-action="previous-key" title="Previous key">‹◆</button><button data-scene-action="next-key" title="Next key">◆›</button><button data-scene-action="keyframe">◇ Keyframe pose</button><label><input class="scene-auto-key" type="checkbox">Auto key</label><span class="scene-key-label">Select a key</span><label>To next key <select class="scene-key-interpolation" disabled>${Object.entries(INTERPOLATIONS).map(([key,label])=>`<option value="${key}">${label}</option>`).join('')}</select></label><button data-scene-action="delete-key" title="Delete selected key">Delete key</button><svg class="scene-easing-curve" viewBox="0 0 84 28" aria-label="Selected interpolation curve"><path/></svg></div><div class="scene-dope-sheet" aria-label="Scene animation dope sheet"></div></div>
      <div class="scene-footer"><button data-scene-action="play" aria-label="Play scene animation">▶</button><label>Frame <input class="scene-current-frame" type="number" min="1" value="1" step="1"></label><input class="scene-frame-slider" aria-label="Scene frame" type="range" min="1" value="1"><label>End <input class="scene-end-frame" type="number" min="1" max="7200" step="1"></label><label class="scene-samples">Samples <select><option value="4">4 · Draft</option><option value="16">16 · Preview</option><option value="32">32 · Standard</option><option value="64">64 · Fine</option><option value="128">128 · Final</option><option value="256">256 · Final+</option></select></label><button class="scene-render primary" data-scene-action="render">Render scene ↗</button></div>
      <div class="scene-footnote">Z-up · XYZ rotations · The scene and motion are saved with your film · Viewport lighting is approximate; render uses Cycles</div>
      <dialog class="scene-import-dialog" aria-labelledby="scene-import-title"><form class="scene-import-form"><h3 id="scene-import-title">Import a polygon mesh</h3><p>Choose one OBJ and optional matching MTL files. Mesh parts retain their solid materials and UV coordinates. Texture images are not imported.</p><label>Geometry and materials<input data-scene-import-file type="file" accept=".obj,.mtl" multiple required></label><div class="scene-import-files" aria-live="polite">OBJ up to 5 MiB · MTL files together up to 1 MiB</div><div class="scene-import-options"><label>Source up axis<select data-scene-import-axis><option value="Z">Z up</option><option value="Y">Y up</option></select></label><label>Import scale<input data-scene-import-scale type="number" value="1" min="0.000001" max="10000" step="any" required></label></div><p class="scene-import-status" role="status"></p><div class="scene-import-actions"><button type="button" data-scene-import-cancel>Cancel</button><button type="submit" class="primary" data-scene-import-submit>Import mesh</button></div></form></dialog></section>`;
    const root=host.querySelector('.scene-editor'),canvas=root.querySelector('canvas'),viewport=root.querySelector('.scene-viewport');
    const inspector=root.querySelector('.scene-inspector'),outliner=root.querySelector('.scene-outliner'),message=root.querySelector('.scene-message'),dope=root.querySelector('.scene-dope-sheet');
    let gl,program,locations={},meshes={},lineBuffer,normalBuffer,resizeObserver,gizmo=null;
    const importDialog=root.querySelector('.scene-import-dialog'),importStatus=root.querySelector('.scene-import-status');
    const removers=[],listen=(el,event,fn,options)=>{el.addEventListener(event,fn,options);return ()=>el.removeEventListener(event,fn,options);};
    const capture=pointerId=>{try{root.setPointerCapture?.(pointerId);}catch(_){};};
    const report=(text,error=false)=>{message.textContent=text;message.classList.toggle('error',error);message.hidden=!text;};
    const getItem=(type,id)=>type==='object'?scene.objects.find(o=>o.id===id):type==='light'?scene.lights.find(o=>o.id===id):type==='world'?scene.world:scene.camera;
    const selectedItem=()=>getItem(selected.type,selected.id);
    const animated=()=>['object','camera','light'].includes(selected.type);
    const cameraPose=()=>poseAt(scene.camera,frame,'camera');
    const eye=()=>viewCamera?cameraPose().position:add(orbit.target,[Math.cos(orbit.azimuth)*Math.cos(orbit.elevation)*orbit.distance,Math.sin(orbit.azimuth)*Math.cos(orbit.elevation)*orbit.distance,Math.sin(orbit.elevation)*orbit.distance]);
    const target=()=>viewCamera?cameraPose().target:orbit.target;
    const tracks=()=>[...scene.objects.map(item=>({type:'object',id:item.id,name:item.name,item})),{type:'camera',id:'camera',name:'Render camera',item:scene.camera},...scene.lights.map(item=>({type:'light',id:item.id,name:item.name,item}))];
    function publish(before) {
      try {if(bridge.onChange?.(copy(scene))===false){if(before)scene=before;report('Finish the current project operation before editing.',true);refresh();return false;}}
      catch(error){if(before)scene=before;report(error.message||'Scene change could not be saved.',true);refresh();return false;}
      revision++;refresh();return true;
    }
    function commit(change) {const before=copy(scene);try{change();report('');return publish(before);}catch(error){scene=before;report(error.message,true);refresh();return false;}}
    function ensureKey(item,kind,at=frame) {
      item.keyframes??=[];let key=item.keyframes.find(k=>k.frame===at);
      if(!key){if(item.keyframes.length>=128)throw Error('This item already has 128 keys. Remove a key before adding another.');key={frame:at,interpolation:'linear',...poseAt(item,at,kind)};item.keyframes.push(key);item.keyframes.sort((a,b)=>a.frame-b.frame);}
      return key;
    }
    function writePose(item,kind,pose) {const destination=autoKey||item.keyframes.length?ensureKey(item,kind):item;for(const prop of POSE_FIELDS[kind])destination[prop]=copy(pose[prop]);}
    function updateFrameUI() {root.querySelector('.scene-current-frame').value=frame;root.querySelector('.scene-frame-slider').value=frame;dope.style.setProperty('--scene-playhead',`${(frame-1)/Math.max(1,scene.frame_end-1)*100}%`);}
    function setFrame(value) {frame=clamp(Math.round(Number(value)||1),1,scene.frame_end);updateFrameUI();if(!playing)renderInspector();draw();}
    function stop() {playing=false;cancelAnimationFrame(animation);root.querySelector('[data-scene-action="play"]').textContent='▶';}
    function play() {if(playing){stop();renderInspector();return;}if(gesture)return;playing=true;root.querySelector('[data-scene-action="play"]').textContent='Ⅱ';const start=performance.now(),initial=frame;function tick(now){if(!playing||disposed)return;setFrame(1+(initial-1+Math.floor((now-start)*opts.fps/1000))%scene.frame_end);animation=requestAnimationFrame(tick);}animation=requestAnimationFrame(tick);}
    function select(type,id) {selected={type,id:id||type};selectedKey=null;if(type!=='object')tool='move';refresh();}
    function addPrimitive(type) {
      if(scene.objects.length>=96){report('A scene supports at most 96 objects.',true);return;}
      commit(()=>{const item={id:uid(),name:type[0].toUpperCase()+type.slice(1)+' '+(scene.objects.length+1),type,position:[0,0,type==='plane'?0:1],rotation:[0,0,0],scale:type==='plane'?[5,5,1]:[1,1,1],material:{color:type==='plane'?'#727a88':'#d8a85f',roughness:.45,metallic:0},keyframes:[]};scene.objects.push(item);selected={type:'object',id:item.id};selectedKey=null;});
    }
    const number=(label,path,value,step=.1,min=-1000,max=1000)=>`<label>${label}<input data-scene-property="${path}" type="number" value="${Number(value).toFixed(step<1?2:0)}" step="${step}" min="${min}" max="${max}"></label>`;
    const vector=(label,path,values,step=.1,min=-1000,max=1000)=>`<fieldset><legend>${label}</legend><div class="scene-vector">${['X','Y','Z'].map((name,i)=>number(name,path+'.'+i,values[i],step,min,max)).join('')}</div></fieldset>`;
    function renderOutliner() {
      outliner.innerHTML=`<h3>Scene <span>${scene.objects.length} objects</span></h3><div class="scene-object-list">${tracks().map(t=>`<button class="${selected.type===t.type&&selected.id===t.id?'selected':''}" data-scene-select="${t.type}" data-id="${esc(t.id)}"><span>${t.type==='camera'?'▱':t.type==='light'?'☀':'◇'}</span>${esc(t.name)}<small>${t.item.keyframes.length?'◆ '+t.item.keyframes.length:t.type}</small></button>`).join('')}<button class="${selected.type==='world'?'selected':''}" data-scene-select="world"><span>◉</span>World</button></div>`;
    }
    function renderInspector() {
      const item=selectedItem();if(!item){selected={type:'camera',id:'camera'};return renderInspector();}
      const pose=animated()?poseAt(item,frame,selected.type):null;let html='';
      if(selected.type==='object')html=`<div class="scene-inspector-heading"><h3>Object</h3><div><button data-scene-action="duplicate">Duplicate</button><button data-scene-action="delete">Delete</button></div></div><label>Name<input data-scene-property="name" value="${esc(item.name)}" maxlength="120"></label>${vector('Position','position',pose.position)}${vector('Rotation · degrees','rotation',pose.rotation,1,-3600,3600)}${vector('Scale','scale',pose.scale,.1,.01,100)}<fieldset><legend>Material</legend><label>Base color<input data-scene-property="material.color" type="color" value="${esc(item.material.color)}"></label>${number('Roughness','material.roughness',item.material.roughness,.05,0,1)}${number('Metallic','material.metallic',item.material.metallic,.05,0,1)}</fieldset>`;
      else if(selected.type==='camera')html=`<h3>Render camera</h3>${vector('Position','position',pose.position)}${vector('Look at','target',pose.target)}${number('Vertical field of view','fov',pose.fov,1,10,100)}<p class="scene-explanation">Keyframe the position, aim and lens to create camera moves. Camera view follows the animated shot.</p>`;
      else if(selected.type==='light')html=`<div class="scene-inspector-heading"><h3>Light</h3><button data-scene-action="delete">Delete</button></div><label>Name<input data-scene-property="name" value="${esc(item.name)}" maxlength="120"></label><label>Type<select data-scene-property="type">${['area','point','sun'].map(t=>`<option ${item.type===t?'selected':''} value="${t}">${t}</option>`).join('')}</select></label>${vector('Position','position',pose.position)}${item.type!=='point'?vector('Look at','target',pose.target):''}<label>Color<input type="color" data-scene-property="color" value="${esc(item.color)}"></label>${number(item.type==='sun'?'Strength':'Power · watts','power',pose.power,item.type==='sun'?.1:25,0,10000)}${number(item.type==='sun'?'Angular size · degrees':'Size · scene units','size',pose.size,.1,.01,100)}`;
      else html=`<h3>World</h3><label>Environment color<input type="color" data-scene-property="color" value="${esc(item.color)}"></label>${number('Environment strength','strength',item.strength,.05,0,5)}`;
      if(selected.type==='object'&&item.type==='mesh')html+=`<div class="scene-mesh-info"><h4>Imported geometry</h4><p>${item.mesh.vertices.length.toLocaleString()} vertices · ${item.mesh.triangles.length.toLocaleString()} triangles</p><p>${item.mesh.uvs?.length?'UV coordinates retained':'No UV coordinates'} · ${item.mesh.normals?.length?'Corner normals retained':'Face normals'}</p>${item.mesh.source?`<p title="${esc(item.mesh.source.sha256)}">${esc(item.mesh.source.name)}</p>`:''}</div>`;
      if(animated())html+=`<div class="scene-keyframes"><h4>Motion <span>${item.keyframes.length} keys</span></h4><p>${item.keyframes.length?'Pose edits update a key at frame '+frame+'.':'Enable Auto key or add a pose key to begin animation.'} Drag diamonds in the motion tracks to retime. Hold keeps the preceding pose until the next key.</p></div>`;
      inspector.innerHTML=html;
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
      if(disposed)return;clean();frame=clamp(frame,1,scene.frame_end);if(!selectedItem())selected={type:'camera',id:'camera'};
      if(selectedKey){const item=getItem(selectedKey.type,selectedKey.id);if(!item||(selectedKey.frame!==1&&!item.keyframes.some(k=>k.frame===selectedKey.frame)))selectedKey=null;}
      renderOutliner();renderInspector();renderDopeSheet();
      root.querySelector('.scene-current-frame').max=scene.frame_end;root.querySelector('.scene-frame-slider').max=scene.frame_end;root.querySelector('.scene-end-frame').value=scene.frame_end;root.querySelector('.scene-samples select').value=String(scene.samples);
      root.querySelector('.scene-render').disabled=renderBusy||importBusy||!opts.renderAvailable||!scene.objects.length;
      root.querySelector('[data-scene-action="import-obj"]').disabled=importBusy||typeof bridge.onImportMesh!=='function';
      root.querySelector('.scene-render').title=opts.renderAvailable?'Render this authored scene into your media bin':'The Blender render engine is unavailable. Check engines to configure it.';
      root.querySelector('[data-scene-action="keyframe"]').disabled=!animated();root.querySelector('.scene-empty').hidden=!!scene.objects.length;
      root.querySelector('.scene-view-label').innerHTML=(viewCamera?'RENDER CAMERA':'PERSPECTIVE')+' <span>3D scene · '+(viewCamera?'Animated framing':'World axes')+'</span>';
      root.querySelector('[data-scene-action="camera"]').classList.toggle('active',viewCamera);
      for(const button of root.querySelectorAll('[data-scene-tool]')){button.classList.toggle('active',button.dataset.sceneTool===tool);button.disabled=!animated()||(selected.type!=='object'&&button.dataset.sceneTool!=='move');}
      pruneMeshes();draw();
    }
    function initGL() {
      gl=canvas.getContext('webgl',{antialias:true,alpha:false,preserveDrawingBuffer:true});if(!gl){report('WebGL is unavailable. Scene controls and rendering remain available.',true);return;}
      function shader(type,source){const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;}
      program=gl.createProgram();const vs=shader(gl.VERTEX_SHADER,vertexShader),fs=shader(gl.FRAGMENT_SHADER,fragmentShader);gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);gl.deleteShader(vs);gl.deleteShader(fs);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));
      for(const name of ['aPosition','aNormal'])locations[name]=gl.getAttribLocation(program,name);
      for(const name of ['uModel','uViewProjection','uNormal','uColor','uEye','uWorld','uRoughness','uMetallic','uUnlit','uLightCount','uLightPosition[0]','uLightColor[0]','uLightParameters[0]'])locations[name]=gl.getUniformLocation(program,name);
      for(const type of ['cube','sphere','plane','cylinder'])meshes[type]=uploadGeometry(geometry(type));
      lineBuffer=gl.createBuffer();normalBuffer=gl.createBuffer();gl.enable(gl.DEPTH_TEST);gl.disable(gl.CULL_FACE);
    }
    function uploadGeometry(data) {const p=gl.createBuffer(),n=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,p);gl.bufferData(gl.ARRAY_BUFFER,data.vertices,gl.STATIC_DRAW);gl.bindBuffer(gl.ARRAY_BUFFER,n);gl.bufferData(gl.ARRAY_BUFFER,data.normals,gl.STATIC_DRAW);return {...data,bounds:geometryBounds(data.vertices),p,n,count:data.vertices.length/3};}
    function objectGeometry(obj) {const key=obj.type==='mesh'?'mesh:'+obj.mesh.sha256:obj.type;if(!meshes[key]&&gl)meshes[key]=uploadGeometry(meshGeometry(obj.mesh));return meshes[key];}
    function pruneMeshes() {if(!gl)return;const used=new Set(scene.objects.filter(obj=>obj.type==='mesh').map(obj=>'mesh:'+obj.mesh.sha256));for(const key of Object.keys(meshes))if(key.startsWith('mesh:')&&!used.has(key)){gl.deleteBuffer(meshes[key].p);gl.deleteBuffer(meshes[key].n);delete meshes[key];}}
    function frameSelection() {const item=selectedItem();viewCamera=false;if(selected.type==='object'){
      const pose=poseAt(item,frame),data=objectGeometry(item)||{bounds:item.type==='mesh'?geometryBounds(meshGeometry(item.mesh).vertices):geometryBounds(geometry(item.type).vertices)},bounds=data.bounds;
      orbit.target=transform(modelMatrix(pose),bounds.center).slice(0,3);orbit.distance=clamp(bounds.radius*Math.max(...pose.scale)/Math.sin(22.5*deg)*1.2,.2,2000);
    }else {orbit.target=animated()?poseAt(item,frame,selected.type).position:[0,0,1];orbit.distance=13;}}
    function bind(mesh) {gl.bindBuffer(gl.ARRAY_BUFFER,mesh.p);gl.enableVertexAttribArray(locations.aPosition);gl.vertexAttribPointer(locations.aPosition,3,gl.FLOAT,false,0,0);gl.bindBuffer(gl.ARRAY_BUFFER,mesh.n);gl.enableVertexAttribArray(locations.aNormal);gl.vertexAttribPointer(locations.aNormal,3,gl.FLOAT,false,0,0);}
    function lines(points,rgb,model=identity()) {if(!points.length)return;gl.bindBuffer(gl.ARRAY_BUFFER,lineBuffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(points),gl.DYNAMIC_DRAW);gl.bindBuffer(gl.ARRAY_BUFFER,normalBuffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(points.length),gl.DYNAMIC_DRAW);bind({p:lineBuffer,n:normalBuffer});gl.uniformMatrix4fv(locations.uModel,false,model);gl.uniformMatrix3fv(locations.uNormal,false,[1,0,0,0,1,0,0,0,1]);gl.uniform3fv(locations.uColor,rgb);gl.uniform1f(locations.uUnlit,1);gl.drawArrays(gl.LINES,0,points.length/3);}
    function viewInfo() {
      const r=canvas.getBoundingClientRect();let width=r.width,height=r.height;
      if(viewCamera){const aspect=scene.width/scene.height;if(width/height>aspect)width=height*aspect;else height=width/aspect;}
      const e=eye(),look=target(),fov=viewCamera?cameraPose().fov:45,forward=norm(sub(look,e));let up=[0,0,1];if(Math.abs(dot(forward,up))>.999)up=[0,1,0];
      const right=norm(cross(forward,up));up=norm(cross(right,forward));
      return {width,height,ox:(r.width-width)/2,oy:(r.height-height)/2,eye:e,target:look,fov,forward,right,up,vp:matrixProduct(perspective(fov,width/height),lookAt(e,look))};
    }
    function project(point,view) {const p=transform(view.vp,point);if(p[3]<=.05)return null;return {x:view.ox+(p[0]/p[3]+1)*view.width/2,y:view.oy+(1-p[1]/p[3])*view.height/2,z:p[3]};}
    function ray(x,y,view) {const tx=(2*(x-view.ox)/view.width-1)*Math.tan(view.fov*deg/2)*view.width/view.height,ty=(1-2*(y-view.oy)/view.height)*Math.tan(view.fov*deg/2);return {origin:view.eye,direction:norm(add(view.forward,add(mul(view.right,tx),mul(view.up,ty))))};}
    function axisParameter(pointer,origin,axis) {const b=dot(axis,pointer.direction),w=sub(origin,pointer.origin),den=1-b*b;return Math.abs(den)<.015?null:(b*dot(pointer.direction,w)-dot(axis,w))/den;}
    function planePoint(pointer,origin,normal) {const den=dot(pointer.direction,normal);if(Math.abs(den)<.025)return null;return add(pointer.origin,mul(pointer.direction,dot(sub(origin,pointer.origin),normal)/den));}
    function cameraGuide() {const c=cameraPose(),direction=norm(sub(c.target,c.position));let right=norm(cross(direction,[0,0,1]));if(Math.hypot(...right)<.01)right=[1,0,0];const up=norm(cross(right,direction)),center=add(c.position,mul(direction,1.3)),h=1.3*Math.tan(c.fov*deg/2),w=h*scene.width/scene.height,corners=[[-1,-1],[1,-1],[1,1],[-1,1]].map(([x,y])=>add(add(center,mul(right,w*x)),mul(up,h*y))),points=[];for(let i=0;i<4;i++)points.push(...c.position,...corners[i],...corners[i],...corners[(i+1)%4]);lines(points,[.37,.56,.72]);}
    function drawGizmo(view) {
      for(const button of root.querySelectorAll('[data-scene-axis]'))button.hidden=true;gizmo=null;
      const item=selectedItem();if(!animated()||!item||playing||(viewCamera&&selected.type==='camera'))return;
      const pose=poseAt(item,frame,selected.type),origin=pose.position,center=project(origin,view);if(!center)return;
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
      gl.enable(gl.DEPTH_TEST);gizmo={origin,pose,center,length,view,paths};
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
      for(const obj of scene.objects){const pose=poseAt(obj,frame),mesh=objectGeometry(obj);if(!mesh)continue;bind(mesh);gl.uniformMatrix4fv(locations.uModel,false,modelMatrix(pose));gl.uniformMatrix3fv(locations.uNormal,false,normalMatrix(pose));gl.uniform3fv(locations.uColor,color(obj.material.color));gl.uniform1f(locations.uRoughness,obj.material.roughness);gl.uniform1f(locations.uMetallic,obj.material.metallic);gl.uniform1f(locations.uUnlit,0);gl.drawArrays(gl.TRIANGLES,0,mesh.count);}
      if(!viewCamera)for(const light of scene.lights){const p=poseAt(light,frame,'light').position,r=.17;lines([p[0]-r,p[1],p[2],p[0]+r,p[1],p[2],p[0],p[1]-r,p[2],p[0],p[1]+r,p[2],p[0],p[1],p[2]-r,p[0],p[1],p[2]+r],[.9,.77,.42]);}
      drawGizmo(view);gl.disable(gl.SCISSOR_TEST);
    }
    function pick(x,y) {
      const view=viewInfo();if(x<view.ox||y<view.oy||x>view.ox+view.width||y>view.oy+view.height)return;let best=null;const pointer=ray(x,y,view);
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
      gesture={kind:'transform',before:copy(scene),selected:{...selected},frame,axis,axisName,tool,startX:x,startY:y,...gizmo,changed:false,pointerId:event.pointerId};
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
      try {writePose(item,g.selected.type,pose);g.changed=true;renderInspector();draw();}catch(error){report(error.message,true);finishGesture(false);}
    }
    function finishGesture(accept=true) {
      const g=gesture;if(!g)return;gesture=null;if(root.hasPointerCapture?.(g.pointerId))root.releasePointerCapture(g.pointerId);
      if(!accept){scene=g.before;selected=g.selected||selected;frame=g.frame??frame;selectedKey=g.originalSelectedKey||null;report('Gesture cancelled.');refresh();return;}
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
    function propertyChanged(event) {
      const input=event.target.closest('[data-scene-property]');if(!input)return;stop();const item=selectedItem();if(!item)return;
      let value=input.type==='number'?Number(input.value):input.value;if(input.type==='number'){if(!Number.isFinite(value)){refresh();return;}value=clamp(value,Number(input.min),Number(input.max));}
      if(input.dataset.sceneProperty==='name'&&!value.trim()){refresh();return;}
      commit(()=>{const path=input.dataset.sceneProperty.split('.'),isPose=animated()&&POSE_FIELDS[selected.type].includes(path[0]);let destination=isPose?poseAt(item,frame,selected.type):item;const pose=destination;for(let i=0;i<path.length-1;i++)destination=destination[path[i]];destination[path.at(-1)]=value;if(isPose)writePose(item,selected.type,pose);});
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
      if(performance.now()<suppressClick)return;const addButton=event.target.closest('[data-scene-add]');if(addButton){addPrimitive(addButton.dataset.sceneAdd);return;}
      const selectButton=event.target.closest('[data-scene-select]');if(selectButton){select(selectButton.dataset.sceneSelect,selectButton.dataset.id);return;}
      const toolButton=event.target.closest('[data-scene-tool]');if(toolButton){tool=toolButton.dataset.sceneTool;refresh();return;}
      const keyButton=event.target.closest('[data-scene-key]');if(keyButton){const lane=keyButton.closest('.scene-key-lane');selected={type:lane.dataset.trackType,id:lane.dataset.trackId};selectedKey={...selected,frame:Number(keyButton.dataset.sceneKey)};stop();setFrame(selectedKey.frame);refresh();return;}
      const command=event.target.closest('[data-scene-action]')?.dataset.sceneAction;if(!command)return;
      if(command==='play'){play();return;}
      if(command==='camera'){viewCamera=!viewCamera;refresh();return;}
      if(command==='use-camera'){const position=eye(),aim=[...target()],fov=viewCamera?cameraPose().fov:45;commit(()=>{writePose(scene.camera,'camera',{position,target:aim,fov});viewCamera=true;selected={type:'camera',id:'camera'};selectedKey=null;tool='move';});return;}
      if(command==='import-obj'){if(importBusy||typeof bridge.onImportMesh!=='function')return;stop();importStatus.textContent='';importDialog.showModal();return;}
      if(command==='fit'){frameSelection();refresh();return;}
      if(command==='delete'){if(!['object','light'].includes(selected.type))return;commit(()=>{if(selected.type==='object')scene.objects=scene.objects.filter(o=>o.id!==selected.id);else scene.lights=scene.lights.filter(o=>o.id!==selected.id);selected={type:'camera',id:'camera'};selectedKey=null;tool='move';});return;}
      if(command==='duplicate'){if(selected.type!=='object')return;commit(()=>{if(scene.objects.length>=96)throw Error('A scene supports at most 96 objects.');const item=copy(selectedItem());item.id=uid();item.name=(item.name+' copy').slice(0,120);item.position[0]=clamp(item.position[0]+2,-1000,1000);for(const key of item.keyframes)key.position[0]=clamp(key.position[0]+2,-1000,1000);checkGeometryBudget([...scene.objects,item]);scene.objects.push(item);selected={type:'object',id:item.id};selectedKey=null;});return;}
      if(command==='add-light'){commit(()=>{if(scene.lights.length>=16)throw Error('A scene supports at most 16 lights.');const light={id:uid(),name:'Light '+(scene.lights.length+1),type:'area',position:[3,-4,7],target:[0,0,0],color:'#ffffff',power:1000,size:4,keyframes:[]};scene.lights.push(light);selected={type:'light',id:light.id};selectedKey=null;tool='move';});return;}
      if(command==='keyframe'){if(!animated())return;commit(()=>{ensureKey(selectedItem(),selected.type);selectedKey={...selected,frame};});return;}
      if(command==='delete-key'){if(!selectedKey)return;commit(()=>{const item=getItem(selectedKey.type,selectedKey.id);item.keyframes=item.keyframes.filter(k=>k.frame!==selectedKey.frame);selectedKey=null;});return;}
      if(command==='previous-key'||command==='next-key'){if(!animated())return;const keys=[1,...selectedItem().keyframes.map(k=>k.frame)].sort((a,b)=>a-b),next=command==='previous-key'?[...keys].reverse().find(k=>k<frame):keys.find(k=>k>frame);if(next!==undefined){stop();setFrame(next);}return;}
      if(command==='render'){if(!opts.renderAvailable||!scene.objects.length||renderBusy||importBusy)return;renderBusy=true;stop();refresh();try{await bridge.onRender?.({scene:copy(scene),frame_start:1,frame_end:scene.frame_end});report('');}catch(error){report(error.message||'Scene render could not start.',true);}finally{renderBusy=false;refresh();}}
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
      if(handle&&['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();event.stopPropagation();const index='xyz'.indexOf(handle.dataset.sceneAxis),direction=['ArrowLeft','ArrowDown'].includes(event.key)?-1:1;commit(()=>{const item=selectedItem(),pose=poseAt(item,frame,selected.type),property=tool==='move'?'position':tool==='rotate'?'rotation':'scale',step=tool==='rotate'?15:tool==='scale'?.1:.25,indices=index<0?[0,1,2]:[index];for(const i of indices)pose[property][i]=clamp(pose[property][i]+step*direction,tool==='scale'?.01:tool==='rotate'?-3600:-1000,tool==='scale'?100:tool==='rotate'?3600:1000);writePose(item,selected.type,pose);});return;}
      if(event.metaKey||event.ctrlKey)return;event.stopPropagation();
      if(event.code==='Space'){event.preventDefault();play();}
      else if(['w','e','r'].includes(event.key.toLowerCase())&&animated()){const requested={w:'move',e:'rotate',r:'scale'}[event.key.toLowerCase()];if(selected.type==='object'||requested==='move'){tool=requested;refresh();}}
      else if(event.key.toLowerCase()==='i'&&animated()){event.preventDefault();commit(()=>{ensureKey(selectedItem(),selected.type);selectedKey={...selected,frame};});}
      else if(['Delete','Backspace'].includes(event.key)&&!event.target.closest('button')){event.preventDefault();root.querySelector(`[data-scene-action="${selectedKey?'delete-key':'delete'}"]`)?.click();}
    }));
    removers.push(listen(dope,'pointerdown',event=>{if(event.button!==0||gesture)return;const key=event.target.closest('[data-scene-key]');if(key){beginKeyDrag(event,key);return;}const lane=event.target.closest('.scene-key-lane');if(lane){stop();const rect=lane.getBoundingClientRect();setFrame(1+(event.clientX-rect.left)/rect.width*(scene.frame_end-1));selectedKey=null;renderKeyTools();}}));
    removers.push(listen(viewport,'contextmenu',event=>event.preventDefault()),listen(viewport,'pointerdown',event=>{
      if(![0,1,2].includes(event.button)||gesture)return;const axisButton=event.target.closest('[data-scene-axis]');if(event.target!==canvas&&!axisButton)return;
      event.preventDefault();canvas.focus();const rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top,axis=event.button===0&&!event.shiftKey?(axisButton?.dataset.sceneAxis||hitGizmo(x,y)):null;
      if(axis){beginTransform(event,axis);return;}stop();capture(event.pointerId);
      if(viewCamera){const pose=cameraPose(),d=sub(pose.position,pose.target);orbit={target:[...pose.target],distance:Math.hypot(...d),azimuth:Math.atan2(d[1],d[0]),elevation:Math.asin(d[2]/Math.hypot(...d))};}
      orbitDrag={x:event.clientX,y:event.clientY,initialX:event.clientX,initialY:event.clientY,pan:event.shiftKey||event.button!==0,moved:false,pointerId:event.pointerId};
    }));
    removers.push(listen(root,'pointermove',event=>{
      if(gesture){if(gesture.kind==='transform')transformMove(event);else moveKey(event);return;}if(!orbitDrag)return;
      const d=orbitDrag,dx=event.clientX-d.x,dy=event.clientY-d.y;d.moved||=Math.hypot(event.clientX-d.initialX,event.clientY-d.initialY)>3;if(!d.moved)return;viewCamera=false;
      if(d.pan){const direction=norm(sub(orbit.target,eye())),right=norm(cross(direction,[0,0,1])),up=norm(cross(right,direction)),factor=orbit.distance*.002;orbit.target=add(orbit.target,add(mul(right,-dx*factor),mul(up,dy*factor)));}else{orbit.azimuth-=dx*.008;orbit.elevation=clamp(orbit.elevation+dy*.008,-1.5,1.5);}d.x=event.clientX;d.y=event.clientY;draw();root.querySelector('.scene-view-label').innerHTML='PERSPECTIVE <span>3D scene · World axes</span>';
    }),listen(root,'pointerup',event=>{if(gesture){finishGesture(true);return;}if(!orbitDrag)return;const d=orbitDrag;orbitDrag=null;if(!d.moved){const r=canvas.getBoundingClientRect();pick(event.clientX-r.left,event.clientY-r.top);}if(root.hasPointerCapture?.(event.pointerId))root.releasePointerCapture(event.pointerId);refresh();}),listen(root,'pointercancel',()=>{if(gesture)finishGesture(false);orbitDrag=null;}));
    removers.push(listen(canvas,'wheel',event=>{event.preventDefault();if(gesture)return;if(viewCamera){const pose=cameraPose(),d=sub(pose.position,pose.target);orbit={target:[...pose.target],distance:Math.hypot(...d),azimuth:Math.atan2(d[1],d[0]),elevation:Math.asin(d[2]/Math.hypot(...d))};viewCamera=false;}orbit.distance=clamp(orbit.distance*Math.exp(event.deltaY*.001),.2,2000);refresh();},{passive:false}));
    try{initGL();}catch(error){report('The viewport could not initialize: '+error.message,true);if(gl&&program)gl.deleteProgram(program);gl=null;}
    if(globalThis.ResizeObserver){resizeObserver=new ResizeObserver(draw);resizeObserver.observe(viewport);}else removers.push(listen(window,'resize',draw));
    refresh();
    return {
      setScene(next,options={}){if(gesture)finishGesture(false);stop();opts={...opts,...options};scene=copy(next||defaultScene(opts));revision++;refresh();},
      setRenderAvailable(value){opts.renderAvailable=!!value;refresh();},
      destroy(){disposed=true;stop();resizeObserver?.disconnect();for(const remove of removers)remove();if(gl){for(const mesh of Object.values(meshes)){gl.deleteBuffer(mesh.p);gl.deleteBuffer(mesh.n);}gl.deleteBuffer(lineBuffer);gl.deleteBuffer(normalBuffer);gl.deleteProgram(program);}host.replaceChildren();}
    };
  }
  window.CinematicumSceneEditor={mount,defaultScene,poseAt,easing,meshGeometry,geometryBounds,intersectGeometry};
})();
