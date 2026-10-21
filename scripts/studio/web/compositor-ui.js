/* Editable FFmpeg image graph. No source pixels are fabricated in this workspace. */
(() => {
  'use strict';
  const copy = value => JSON.parse(JSON.stringify(value));
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const number = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
  const CURVE_CHANNELS = ['master','red','green','blue'];
  const CURVE_COLORS = {master:'#e6e8ee',red:'#ed7979',green:'#81c998',blue:'#83a6f4'};
  const IDENTITY = [[0,0],[1,1]], POLYGON = [[.1,.85],[.5,.1],[.9,.85]];
  const POINT_GAP = 1/255+.00001;
  const BLEND_MODES = {normal:'Normal',multiply:'Multiply',screen:'Screen',add:'Add',difference:'Difference'};
  const EASING = {linear:'Linear',constant:'Hold',ease_in:'Ease in',ease_out:'Ease out',ease_in_out:'Ease in / out'};
  const MAX_FRAME=1296000;
  const definitions = {
    source: {name:'Source',inputs:[],color:'#6d9fac',defaults:{},description:'The selected clip, trimmed and fitted to the project canvas. Every branch starts with this image.'},
    grade: {name:'Color grade',inputs:['Image'],color:'#bc9bd3',defaults:{exposure:0,contrast:1,saturation:1,temperature:0},description:'Correct this branch before combining it with other branches.',fields:[['exposure','Exposure · stops',-3,3,.05],['contrast','Contrast',0,3,.05],['saturation','Saturation',0,3,.05],['temperature','Temperature',-1,1,.02]]},
    curves: {name:'Color curves',inputs:['Image'],color:'#bc9bd3',defaults:{master:copy(IDENTITY),red:copy(IDENTITY),green:copy(IDENTITY),blue:copy(IDENTITY)},description:'Shape the master tone curve and individual RGB channels. Channel curves are applied before the master curve.'},
    blur: {name:'Gaussian blur',inputs:['Image'],color:'#82a4ce',defaults:{sigma:2},description:'Blur the image while retaining its existing transparency.',fields:[['sigma','Radius',0,30,.1]]},
    sharpen: {name:'Sharpen',inputs:['Image'],color:'#82a4ce',defaults:{amount:1},description:'Recover edge definition with an unsharp mask.',fields:[['amount','Amount',0,3,.05]]},
    chroma_key: {name:'Chroma key',inputs:['Image'],color:'#80b99b',defaults:{color:'#00ff00',similarity:.18,blend:.08},description:'Remove a selected color. Connect the transparent result to a Merge foreground.',fields:[['similarity','Color similarity',.01,1,.01],['blend','Edge blend',0,1,.01]]},
    mask: {name:'Shape mask',inputs:['Image'],color:'#cfad76',defaults:{shape:'ellipse',x:.5,y:.5,width:.65,height:.65,rotation:0,feather:.15,invert:false,points:copy(POLYGON)},description:'Choose an ellipse or rectangle, or draw a polygon. Place, rotate, and feather the mask over this branch.',fields:[['x','Center X',0,1,.01],['y','Center Y',0,1,.01],['width','Width',.01,2,.01],['height','Height',.01,2,.01],['rotation','Rotation · degrees',-360,360,1],['feather','Inward feather',0,1,.01]]},
    merge: {name:'Merge',inputs:['Background','Foreground'],color:'#d39c84',defaults:{opacity:1,mode:'normal'},description:'Blend the foreground over the background. Each branch’s transparency and foreground opacity determine its contribution.',fields:[['opacity','Foreground opacity',0,1,.01]]}
  };
  const animationFields=type=>type==='sharpen'?[]:[...(definitions[type].fields||[]).map(field=>field[0]),...(type==='mask'?['points']:[])];
  const parameterName=(type,name)=>name==='points'?'Polygon path':definitions[type].fields?.find(field=>field[0]===name)?.[1]||name;
  const validPoints=(points,min,max)=>Array.isArray(points)&&points.length>=min&&points.length<=max&&points.every(point=>Array.isArray(point)&&point.length===2&&point.every(value=>typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=1));
  const validPolygon=points=>validPoints(points,3,24)&&!points.some((point,i)=>Math.hypot(point[0]-points[(i+1)%points.length][0],point[1]-points[(i+1)%points.length][1])<.00001);
  const NODE_WIDTH = 174;
  const nodeHeight = node => node.type === 'source' ? 132 : node.type === 'merge' ? 120 : 110;
  const freshGraph = () => ({version:1,nodes:[{id:'source',type:'source',inputs:[],params:{},position:{x:42,y:62}}],output:'source'});
  function validate(graph,timing={}) {
    if (!graph || graph.version !== 1 || !Array.isArray(graph.nodes) || !graph.nodes.length || graph.nodes.length > 32) return 'A graph needs 1–32 nodes and version 1.';
    const nodes = new Map(),start=timing.animationStart??0,duration=timing.animationDuration??MAX_FRAME;
    if(!Number.isInteger(start)||start < -MAX_FRAME||start>0||!Number.isInteger(duration)||duration<1||duration>MAX_FRAME)return 'Animation requires a bounded integer frame domain.';
    let keyCount=0,valueCount=0;
    for (const node of graph.nodes) {
      if (!node || typeof node.id !== 'string' || !node.id || nodes.has(node.id)) return 'Every node needs a unique ID.';
      if (!definitions[node.type]) return 'This graph contains an unsupported node.';
      if (!Array.isArray(node.inputs) || node.inputs.length !== definitions[node.type].inputs.length) return `${definitions[node.type].name} has the wrong number of inputs.`;
      const p={...definitions[node.type].defaults,...node.params};
      for(const [name,,min,max]of definitions[node.type].fields||[])if(typeof p[name]!=='number'||!Number.isFinite(p[name])||p[name]<min||p[name]>max)return `${parameterName(node.type,name)} must be a finite value between ${min} and ${max}.`;
      if(node.type==='curves')for(const channel of CURVE_CHANNELS){const points=p[channel];if(!validPoints(points,2,12)||points[0][0]!==0||points.at(-1)[0]!==1||points.some((point,i)=>i&&point[0]-points[i-1][0]<1/255-1e-9))return 'Curve points need distinct, increasing inputs from 0 to 1.';}
      if(node.type==='mask'&&(!['ellipse','rectangle','polygon'].includes(p.shape)||!validPolygon(p.points)))return 'A mask polygon needs 3–24 distinct neighboring vertices.';
      if(node.type==='merge'&&!BLEND_MODES[p.mode])return 'Choose an available blend mode.';
      if(node.tracking_source!==undefined){
        const source=node.tracking_source;
        if(node.type!=='mask'||!source||typeof source!=='object'||Array.isArray(source)||Object.keys(source).sort().join(',')!=='backend,sha256,version'||source.version!==1||typeof source.sha256!=='string'||!/^[0-9a-fA-F]{64}$/.test(source.sha256)||typeof source.backend!=='string'||[...source.backend].length>160)return 'Mask tracking provenance requires version 1, a SHA-256 digest, and a backend name up to 160 characters.';
      }
      if(node.animation!==undefined){
        if(!node.animation||typeof node.animation!=='object'||Array.isArray(node.animation))return 'Node animation must contain named property channels.';
        for(const [name,keys]of Object.entries(node.animation)){
          if(!animationFields(node.type).includes(name))return 'This property does not support animation.';
          const maximum=name==='points'?64:128;if(!Array.isArray(keys)||!keys.length||keys.length>maximum)return `${parameterName(node.type,name)} supports 1–${maximum} keys.`;
          const times=new Set();
          for(const key of keys){
            if(!key||typeof key!=='object'||Array.isArray(key)||Object.keys(key).some(name=>!['frame','value','interpolation'].includes(name)))return 'Animation keys support frame, value and interpolation.';
            if(!Number.isInteger(key.frame)||key.frame<start||key.frame>=duration||times.has(key.frame))return 'Key times must be unique integer frames inside the animation domain.';
            if(!Object.hasOwn(EASING,key.interpolation??'linear'))return 'Choose a supported keyframe interpolation.';
            times.add(key.frame);keyCount++;
            if(name==='points'){
              if(!validPolygon(key.value)||key.value.length!==p.points.length)return 'Animated polygon keys must preserve vertex count and order.';
              valueCount+=key.value.length*2;
            }else{
              const [,,min,max]=definitions[node.type].fields.find(field=>field[0]===name);
              if(typeof key.value!=='number'||!Number.isFinite(key.value)||key.value<min||key.value>max)return 'Animated values must stay inside the property limits.';
              valueCount++;
            }
          }
        }
      }
      if(keyCount>1024||valueCount>8192)return 'This graph exceeds its animation budget (1024 keys / 8192 coordinate values).';
      nodes.set(node.id,node);
    }
    if (graph.nodes.filter(node => node.type === 'source').length !== 1) return 'A graph needs exactly one Source node.';
    if (!nodes.has(graph.output)) return 'Choose an existing node as the output.';
    const done = new Set(), visiting = new Set();
    function visit(id) {
      if (!nodes.has(id)) return 'An input refers to a missing node.';
      if (visiting.has(id)) return 'That connection creates a cycle. Images must flow toward the output.';
      if (done.has(id)) return '';
      visiting.add(id);
      for (const input of nodes.get(id).inputs) { const error = visit(input); if (error) return error; }
      visiting.delete(id);done.add(id);return '';
    }
    for (const node of graph.nodes) { const error = visit(node.id); if (error) return error; }
    return '';
  }
  function animationValue(base,keys,frame){
    const byFrame=new Map([[0,{frame:0,value:base,interpolation:'linear'}]]);
    for(const key of keys||[])byFrame.set(key.frame,key);
    const points=[...byFrame.values()].sort((a,b)=>a.frame-b.frame);
    if(frame<=points[0].frame)return copy(points[0].value);
    for(let i=0;i<points.length-1;i++)if(frame<points[i+1].frame){
      const a=points[i],b=points[i+1],t=(frame-a.frame)/(b.frame-a.frame),mode=a.interpolation||'linear';
      const amount=mode==='constant'?0:mode==='ease_in'?t*t:mode==='ease_out'?1-(1-t)**2:mode==='ease_in_out'?t*t*(3-2*t):t;
      const mix=(x,y)=>Array.isArray(x)?x.map((value,i)=>mix(value,y[i])):x+(y-x)*amount;
      return mix(a.value,b.value);
    }
    return copy(points.at(-1).value);
  }
  function paramsAt(node,frame){
    const params=copy({...definitions[node.type].defaults,...node.params});
    for(const [name,keys]of Object.entries(node.animation||{}))params[name]=animationValue(params[name],keys,frame);
    return params;
  }
  function wouldCycle(graph, from, to) {
    const nodes = new Map(graph.nodes.map(node => [node.id,node])), seen = new Set();
    function contains(id) {
      if (id === to) return true;
      if (seen.has(id)) return false;
      seen.add(id);return (nodes.get(id)?.inputs || []).some(contains);
    }
    return contains(from);
  }
  function curveValue(points, x) {
    // Shape-preserving cubic Hermite interpolation, matching the render curve.
    const count=points.length,h=[],d=[],slopes=[];
    for(let i=0;i<count-1;i++){h[i]=points[i+1][0]-points[i][0];d[i]=(points[i+1][1]-points[i][1])/h[i];}
    if(count===2)slopes.push(d[0],d[0]);
    else {
      const end=(h0,h1,d0,d1)=>{const value=((2*h0+h1)*d0-h0*d1)/(h0+h1);return value*d0<=0?0:(d0*d1<0&&Math.abs(value)>Math.abs(3*d0)?3*d0:value);};
      slopes[0]=end(h[0],h[1],d[0],d[1]);slopes[count-1]=end(h[count-2],h[count-3],d[count-2],d[count-3]);
      for(let i=1;i<count-1;i++){const w1=2*h[i]+h[i-1],w2=h[i]+2*h[i-1];slopes[i]=d[i-1]*d[i]<=0?0:(w1+w2)/(w1/d[i-1]+w2/d[i]);}
    }
    let i=0;while(i<count-2&&x>points[i+1][0])i++;
    const t=clamp((x-points[i][0])/h[i],0,1),t2=t*t,t3=t2*t;
    return clamp((2*t3-3*t2+1)*points[i][1]+(t3-2*t2+t)*h[i]*slopes[i]+(-2*t3+3*t2)*points[i+1][1]+(t3-t2)*h[i]*slopes[i+1],0,1);
  }
  function mount(host, bridge = {}) {
    let graph = freshGraph(), context = {}, selected = 'source', inspector = null, pending = null, drag = null;
    let zoom = 1, pan = {x:0,y:0}, destroyed = false, positions = new Map();
    let curveChannel='master',curvePoint=0,polygonPoint=0,editorDrag=null,animationChannel=null;
    host.classList.add('compositor-editor');
    host.innerHTML = `<div class="compositor-toolbar"><span class="compositor-title">NODE COMPOSITOR</span><select data-graph-add-type aria-label="Node type to add">${Object.entries(definitions).filter(([type])=>type!=='source').map(([type,definition])=>`<option value="${type}">${definition.name}</option>`).join('')}</select><button data-graph-action="add" class="small" title="Add after the selected node">＋ Add</button><button data-graph-action="masked" class="quiet small" title="Create a grade, feathered mask, and merge branch">Masked correction</button><span class="compositor-toolbar-spacer"></span><button data-graph-action="fit" class="quiet small" title="Fit all nodes">Fit</button><button data-graph-action="preview" class="small">Render preview ↗</button></div><div class="compositor-stage" tabindex="0" aria-label="Node graph. Drag nodes, or connect an output port to an input port."><div class="compositor-world"><svg class="compositor-wires" aria-hidden="true"></svg><div class="compositor-nodes"></div></div><div class="compositor-empty" hidden><strong>Select a picture clip.</strong><span>Import a video or image, add it to the timeline, then select its clip.</span><button data-graph-action="import" class="small">Import media</button></div><div class="compositor-connection-hint" hidden></div></div><div class="compositor-footer"><span data-graph-status>Source → output</span><span>Drag background to pan · ⌘/Ctrl + wheel to zoom</span><label>Output <select data-graph-output aria-label="Compositor output node"></select></label></div>`;
    const stage=host.querySelector('.compositor-stage'),world=host.querySelector('.compositor-world'),nodesElement=host.querySelector('.compositor-nodes'),wires=host.querySelector('.compositor-wires');
    const notify = (message,error=false) => bridge.toast?.(message,error);
    const nodeById = id => graph.nodes.find(node => node.id===id);
    const currentFrame=()=>Math.round(number(context.frame,number(bridge.getFrame?.(),0)));
    const frameAllowed=frame=>frame>=(context.animationStart??0)&&frame<(context.animationDuration??MAX_FRAME);
    const sourceId = () => graph.nodes.find(node=>node.type==='source')?.id;
    const label = node => `${definitions[node.type]?.name || node.type} ${node.type==='source'?'':graph.nodes.indexOf(node)}`.trim();
    function position(node) { return positions.get(node.id) || {x:0,y:0}; }
    function cachePositions() { positions=new Map(graph.nodes.map((node,index)=>[node.id,{x:number(node.position?.x,42+index*230),y:number(node.position?.y,62)}])); }
    function activeNodes() {const active=new Set();function walk(id){if(active.has(id))return;active.add(id);nodeById(id)?.inputs.forEach(walk);}walk(graph.output);return active;}
    function applyView() {world.style.transform=`translate(${pan.x}px,${pan.y}px) scale(${zoom})`;stage.style.backgroundPosition=`${pan.x}px ${pan.y}px`;stage.style.backgroundSize=`${20*zoom}px ${20*zoom}px`;}
    function portPoint(id, input=null) {const node=nodeById(id),p=positions.get(id);return p&&node?{x:p.x+(input===null?NODE_WIDTH:0),y:p.y+(input===null?54:54+input*24)}:null;}
    function curve(a,b) {const d=Math.max(45,Math.abs(b.x-a.x)*.48);return `M ${a.x} ${a.y} C ${a.x+d} ${a.y}, ${b.x-d} ${b.y}, ${b.x} ${b.y}`;}
    function drawWires(cursor) {
      const active=activeNodes();let paths='';
      for (const node of graph.nodes) node.inputs.forEach((id,index)=>{const a=portPoint(id),b=portPoint(node.id,index);if(a&&b)paths+=`<path class="${active.has(node.id)?'active':''}" d="${curve(a,b)}"></path>`;});
      if(pending&&cursor){const a=portPoint(pending);if(a)paths+=`<path class="pending" d="${curve(a,cursor)}"></path>`;}
      wires.innerHTML=paths;
    }
    function summary(node) {
      const p={...definitions[node.type].defaults,...node.params};
      if(node.type==='source')return context.sourceLabel||'Selected clip';
      if(node.type==='grade')return `${number(p.exposure).toFixed(2)} EV · sat ${number(p.saturation).toFixed(2)}`;
      if(node.type==='curves')return `Master + RGB · ${CURVE_CHANNELS.reduce((sum,name)=>sum+(p[name]?.length||2),0)} points`;
      if(node.type==='blur')return `Radius ${number(p.sigma).toFixed(1)}`;
      if(node.type==='sharpen')return `Amount ${number(p.amount).toFixed(2)}`;
      if(node.type==='chroma_key')return `${p.color} · ${number(p.similarity).toFixed(2)}`;
      if(node.type==='mask')return `${p.shape}${p.invert?' · inverted':''} · feather ${number(p.feather).toFixed(2)}`;
      return `${BLEND_MODES[p.mode]||'Normal'} · ${Math.round(number(p.opacity,1)*100)}%`;
    }
    function renderGraph() {
      const enabled=Boolean(context.key),active=activeNodes();
      host.classList.toggle('graph-unavailable',!enabled);host.querySelector('.compositor-empty').hidden=enabled;
      host.querySelectorAll('[data-graph-action]:not([data-graph-action=import]),[data-graph-add-type],[data-graph-output]').forEach(control=>{control.disabled=!enabled;});
      if(enabled)host.querySelector('[data-graph-action=preview]').disabled=bridge.renderAvailable?.()===false;
      nodesElement.hidden=!enabled;wires.hidden=!enabled;
      nodesElement.innerHTML=graph.nodes.map(node=>{const definition=definitions[node.type]||definitions.source,p=position(node);return `<article class="compositor-node ${selected===node.id?'selected':''} ${graph.output===node.id?'graph-output':''} ${active.has(node.id)?'connected':'disconnected'}" data-node="${escape(node.id)}" data-node-type="${escape(node.type)}" tabindex="0" aria-label="${escape(label(node))}${graph.output===node.id?', output':''}" style="left:${p.x}px;top:${p.y}px;width:${NODE_WIDTH}px;height:${nodeHeight(node)}px;--node-color:${definition.color}"><div class="compositor-node-head"><span>${escape(label(node))}</span><span class="node-output-tag">${graph.output===node.id?'OUT':''}</span></div>${definition.inputs.map((name,index)=>`<button class="node-port node-input" data-node-input="${index}" data-node-target="${escape(node.id)}" style="top:${48+index*24}px" aria-label="Connect ${escape(name)} input of ${escape(label(node))}" title="${escape(name)} input"></button><span class="node-input-label" style="top:${48+index*24}px">${escape(name)}</span>`).join('')}<button class="node-port node-output ${pending===node.id?'pending':''}" data-node-output="${escape(node.id)}" aria-label="Connect output of ${escape(label(node))}" title="Drag or click, then choose an input"></button>${node.type==='source'&&context.sourceThumb?`<img class="node-source-thumb" src="${escape(context.sourceThumb)}" alt="Selected clip thumbnail" draggable="false">`:''}<div class="node-summary" title="${escape(summary(node))}">${escape(summary(node))}</div></article>`;}).join('');
      const error=validate(graph);host.querySelector('[data-graph-status]').textContent=enabled?(error||`${graph.nodes.length} nodes · ${active.size} in output`):'Select a video or image clip';host.querySelector('[data-graph-status]').classList.toggle('invalid',Boolean(error));
      host.querySelector('[data-graph-output]').innerHTML=graph.nodes.map(node=>`<option value="${escape(node.id)}" ${node.id===graph.output?'selected':''}>${escape(label(node))}</option>`).join('');
      const hint=host.querySelector('.compositor-connection-hint');hint.hidden=!pending;hint.textContent=pending?'Choose an input port · Esc cancels':'';
      applyView();drawWires();
    }
    function fit() {
      if(!stage.clientWidth||!stage.clientHeight||!graph.nodes.length)return;
      const bounds=graph.nodes.map(node=>({p:position(node),h:nodeHeight(node)})),minX=Math.min(...bounds.map(n=>n.p.x)),minY=Math.min(...bounds.map(n=>n.p.y)),maxX=Math.max(...bounds.map(n=>n.p.x+NODE_WIDTH)),maxY=Math.max(...bounds.map(n=>n.p.y+n.h));
      zoom=clamp(Math.min((stage.clientWidth-60)/(maxX-minX),(stage.clientHeight-42)/(maxY-minY)),.28,1);
      pan={x:(stage.clientWidth-(maxX-minX)*zoom)/2-minX*zoom,y:(stage.clientHeight-(maxY-minY)*zoom)/2-minY*zoom};applyView();
    }
    function selectNode(id) {if(!nodeById(id))return;selected=id;renderGraph();renderInspector();}
    function commit(next, nextSelected=selected) {
      const error=validate(next,context);if(error){notify(error,true);return false;}
      if(!context.key)return false;
      const previous=graph;graph=copy(next);selected=nextSelected;cachePositions();
      try {if(bridge.onChange?.(copy(graph),context.key)===false){graph=previous;cachePositions();return false;}}catch(error){graph=previous;cachePositions();notify(error.message,true);return false;}
      renderGraph();renderInspector();return true;
    }
    function addNode(type) {
      if(!definitions[type]||type==='source'||!context.key)return;
      if(graph.nodes.length>=32){notify('This clip already has 32 nodes.',true);return;}
      const next=copy(graph),from=nodeById(selected)||nodeById(graph.output),p=position(from),id=crypto.randomUUID();
      next.nodes.push({id,type,inputs:type==='merge'?[sourceId(),from.id]:[from.id],params:copy(definitions[type].defaults),position:{x:p.x+230,y:p.y+(type==='merge'?45:0)}});next.output=id;
      if(commit(next,id))requestAnimationFrame(fit);
    }
    function maskedCorrection() {
      if(graph.nodes.length>29){notify('A masked correction needs three available node slots.',true);return;}
      const next=copy(graph),base=nodeById(selected)||nodeById(graph.output),p=position(base),ids=[crypto.randomUUID(),crypto.randomUUID(),crypto.randomUUID()];
      next.nodes.push({id:ids[0],type:'grade',inputs:[base.id],params:{...definitions.grade.defaults,exposure:.5},position:{x:p.x+230,y:p.y-80}},{id:ids[1],type:'mask',inputs:[ids[0]],params:copy(definitions.mask.defaults),position:{x:p.x+460,y:p.y-80}},{id:ids[2],type:'merge',inputs:[base.id,ids[1]],params:{opacity:1},position:{x:p.x+690,y:p.y+30}});next.output=ids[2];
      if(commit(next,ids[1]))requestAnimationFrame(fit);
    }
    function deleteNode() {
      const node=nodeById(selected);if(!node||node.type==='source')return;
      const next=copy(graph),fallback=node.inputs[0]||sourceId();next.nodes=next.nodes.filter(item=>item.id!==node.id);for(const item of next.nodes)item.inputs=item.inputs.map(id=>id===node.id?fallback:id);if(next.output===node.id)next.output=fallback;commit(next,fallback);
    }
    function duplicateNode() {
      const node=nodeById(selected);if(!node||node.type==='source')return;
      if(graph.nodes.length>=32){notify('This clip already has 32 nodes.',true);return;}
      const next=copy(graph),duplicate=copy(node),p=position(node);duplicate.id=crypto.randomUUID();duplicate.position={x:p.x+30,y:p.y+150};next.nodes.push(duplicate);if(commit(next,duplicate.id))requestAnimationFrame(fit);
    }
    function connect(from,to,input) {
      if(!nodeById(from)||!nodeById(to))return;
      if(wouldCycle(graph,from,to)){notify('That connection would create a cycle. Choose an upstream node.',true);return;}
      const next=copy(graph),node=next.nodes.find(n=>n.id===to);if(input<0||input>=node.inputs.length)return;node.inputs[input]=from;pending=null;commit(next,to);
    }
    function keyButton(node,name){
      if(!animationFields(node.type).includes(name))return '';
      const keyed=node.animation?.[name]?.some(key=>key.frame===currentFrame()),active=!!node.animation?.[name];
      return `<button class="icon-button" data-node-key="${name}" aria-label="${keyed?'Remove':'Set'} ${escape(parameterName(node.type,name))} keyframe" title="${keyed?'Remove':'Set'} key at frame ${currentFrame()}" aria-pressed="${keyed?'true':'false'}" ${frameAllowed(currentFrame())?'':'disabled'} style="font-size:14px;flex:none;color:${active?'var(--accent)':'var(--muted)'}">${keyed?'◆':'◇'}</button>`;
    }
    function parameterControl(name,title,min,max,step,value) {const node=nodeById(selected);return `<div class="node-parameter"><div><label style="flex:1">${escape(title)}</label>${keyButton(node,name)}<input type="number" data-node-param="${name}" min="${min}" max="${max}" step="${step}" value="${Number(value.toFixed(6))}" aria-label="${escape(title)}"></div><input type="range" data-node-param="${name}" min="${min}" max="${max}" step="${step}" value="${value}" aria-label="${escape(title)} slider"></div>`;}
    function animationEditor(node){
      const fields=animationFields(node.type);if(!fields.length)return '';
      if(!fields.includes(animationChannel))animationChannel=Object.keys(node.animation||{})[0]||fields[0];
      const frame=currentFrame(),keys=node.animation?.[animationChannel]||[],key=keys.find(key=>key.frame===frame),active=keys.length>0;
      return `<div class="inspector-section node-animation"><h3>PROPERTY ANIMATION</h3><label>Channel<select data-node-animation-channel aria-label="Animated property">${fields.map(name=>`<option value="${name}" ${name===animationChannel?'selected':''}>${escape(parameterName(node.type,name))}${node.animation?.[name]?' · '+node.animation[name].length+' keys':''}</option>`).join('')}</select></label><div class="field-row"><label>Playhead frame<input data-node-animation-frame type="number" step="1" min="${context.animationStart??0}" max="${(context.animationDuration??MAX_FRAME)-1}" value="${frame}" aria-label="Node animation playhead frame"></label><label>Key interpolation<select data-node-animation-easing ${key?'':'disabled'} aria-label="Node keyframe interpolation">${Object.entries(EASING).map(([value,label])=>`<option value="${value}" ${(key?.interpolation||'linear')===value?'selected':''}>${label}</option>`).join('')}</select></label></div><div class="inspector-actions"><button data-node-key="${animationChannel}" ${frameAllowed(frame)?'':'disabled'}>${key?'◆ Remove key':'◇ Set key'}</button><button data-node-animation-clear ${active?'':'disabled'} title="Keep the current value and remove this channel’s animation">Make static</button></div>${key?`<label>Move key to frame<input data-node-key-time type="number" step="1" min="${context.animationStart??0}" max="${(context.animationDuration??MAX_FRAME)-1}" value="${frame}" aria-label="Move node keyframe"></label>`:''}<div class="keyframe-list" aria-label="Property keyframes">${keys.map(item=>`<span class="keyframe-chip"><button data-node-animation-seek="${item.frame}" title="Go to frame ${item.frame}" ${item.frame===frame?'aria-current="true"':''}>${item.frame===frame?'◆':'◇'} ${item.frame}</button><button data-node-animation-remove="${item.frame}" aria-label="Remove key at frame ${item.frame}">×</button></span>`).join('')}</div><p class="note">${!frameAllowed(frame)?'The playhead is outside this clip’s animation domain. ':''}${active?'Editing this property sets a key at the playhead.':'Set a key to animate this property independently.'} Interpolation applies after a key. Trims preserve the original animation time.</p></div>`;
    }
    function writeParameter(target,name,value,forceKey=false){
      target.params??={};
      if(forceKey||target.animation?.[name]){
        const frame=currentFrame();if(!frameAllowed(frame)){notify('Move the playhead inside the animation domain before setting a key.',true);return false;}
        target.animation??={};const keys=target.animation[name]||[],existing=keys.find(key=>key.frame===frame);
        if(!existing&&keys.length>=(name==='points'?64:128)){notify('This property has reached its keyframe limit.',true);return false;}
        if(existing)existing.value=copy(value);else keys.push({frame,value:copy(value),interpolation:'linear'});
        target.animation[name]=keys.sort((a,b)=>a.frame-b.frame);
      }else target.params[name]=copy(value);
      return true;
    }
    function removeAnimationKey(next,name,frame){
      const target=next.nodes.find(node=>node.id===selected);if(!target?.animation?.[name])return false;
      target.animation[name]=target.animation[name].filter(key=>key.frame!==frame);
      if(!target.animation[name].length)delete target.animation[name];if(!Object.keys(target.animation).length)delete target.animation;
      return true;
    }
    function toggleKey(name){
      const node=nodeById(selected);if(!node||!animationFields(node.type).includes(name))return;
      animationChannel=name;const next=copy(graph),target=next.nodes.find(item=>item.id===selected);
      if(node.animation?.[name]?.some(key=>key.frame===currentFrame()))removeAnimationKey(next,name,currentFrame());
      else if(!writeParameter(target,name,paramsAt(node,currentFrame())[name],true))return;
      commit(next);
    }
    function seekAnimation(frame){
      if(!Number.isInteger(frame)||!frameAllowed(frame)){notify('Choose a frame inside the animation domain.',true);renderInspector();return;}
      const result=bridge.onSeek?.(frame);if(result===false)return;
      context={...context,frame:Number.isFinite(result)?result:frame};renderInspector();
    }
    function canEditPath(){
      const keys=nodeById(selected)?.animation?.points;if(!keys)return true;
      if(!frameAllowed(currentFrame())){notify('Move the playhead inside the animation domain before editing an animated path.',true);return false;}
      if(keys.length>=64&&!keys.some(key=>key.frame===currentFrame())){notify('This path has reached its 64-key limit.',true);return false;}
      return true;
    }
    const editorStyle='width:100%;aspect-ratio:1;display:block;touch-action:none;background:#10141c;border:1px solid #354050;border-radius:6px;cursor:crosshair';
    function editorGrid(curve=false) {
      return [0,.25,.5,.75,1].map(value=>`<path d="M${18+220*value} 18V238 M18 ${18+220*value}H238" fill="none" stroke="#303a49" stroke-width="${value===0||value===1?1:.6}"/>`).join('')+
        (curve?'<path d="M18 238L238 18" stroke="#6b7280" stroke-width=".7" stroke-dasharray="3 4"/>':'')+
        `<text x="128" y="252" text-anchor="middle" fill="#8e9bad" font-size="9">${curve?'INPUT':'LOCAL X'}</text><text x="8" y="128" text-anchor="middle" transform="rotate(-90 8 128)" fill="#8e9bad" font-size="9">${curve?'OUTPUT':'LOCAL Y'}</text>`;
    }
    function curveGraphic(points) {
      const color=CURVE_COLORS[curveChannel],path=Array.from({length:129},(_,i)=>{const x=i/128;return `${i?'L':'M'}${18+220*x} ${238-220*curveValue(points,x)}`;}).join(' ');
      return editorGrid(true)+`<path d="${path}" fill="none" stroke="${color}" stroke-width="2"/>`+points.map((point,index)=>`<circle data-curve-point="${index}" cx="${18+220*point[0]}" cy="${238-220*point[1]}" r="${index===curvePoint?5.7:4.3}" fill="${index===curvePoint?color:'#10141c'}" stroke="${color}" stroke-width="1.6" tabindex="0" role="button" aria-label="Curve point ${index+1}, input ${point[0].toFixed(3)}, output ${point[1].toFixed(3)}" style="cursor:grab"><title>Input ${point[0].toFixed(3)} · Output ${point[1].toFixed(3)}</title></circle>`).join('');
    }
    function polygonGraphic(points) {
      return editorGrid()+`<polygon points="${points.map(point=>`${18+220*point[0]},${18+220*point[1]}`).join(' ')}" fill="#cfad76" fill-opacity=".15" fill-rule="evenodd" stroke="#cfad76" stroke-width="1.8"/>`+points.map((point,index)=>`<circle data-polygon-point="${index}" cx="${18+220*point[0]}" cy="${18+220*point[1]}" r="${index===polygonPoint?5.7:4.3}" fill="${index===polygonPoint?'#cfad76':'#10141c'}" stroke="#cfad76" stroke-width="1.6" tabindex="0" role="button" aria-label="Polygon vertex ${index+1}, X ${point[0].toFixed(3)}, Y ${point[1].toFixed(3)}" style="cursor:grab"><title>Vertex ${index+1}</title></circle>`).join('');
    }
    function curveEditor(params) {
      const points=params[curveChannel]||IDENTITY;curvePoint=clamp(curvePoint,0,points.length-1);const point=points[curvePoint],end=curvePoint===0||curvePoint===points.length-1;
      return `<div class="inspector-section node-curve-editor"><label>Channel<select data-curve-channel aria-label="Curve channel">${CURVE_CHANNELS.map(channel=>`<option value="${channel}" ${channel===curveChannel?'selected':''}>${channel==='master'?'Master · RGB':channel[0].toUpperCase()+channel.slice(1)}</option>`).join('')}</select></label><svg data-curve-editor viewBox="0 0 256 256" tabindex="0" role="group" aria-label="Editable ${curveChannel} tone curve" style="${editorStyle};margin-top:12px">${curveGraphic(points)}</svg><p class="note">Click to add a point; drag to shape the curve. Arrow keys nudge the selected point.</p><div class="field-row"><label>Input<input data-curve-coordinate="0" type="number" min="${end?point[0]:points[curvePoint-1][0]+POINT_GAP}" max="${end?point[0]:points[curvePoint+1][0]-POINT_GAP}" step=".001" value="${point[0]}" ${end?'disabled':''}></label><label>Output<input data-curve-coordinate="1" type="number" min="0" max="1" step=".001" value="${point[1]}"></label></div><div class="inspector-actions"><button data-node-action="curve-remove" ${end?'disabled':''}>Remove point</button><button data-node-action="curve-reset">Reset channel</button></div></div>`;
    }
    function polygonEditor(params) {
      const points=params.points||POLYGON;polygonPoint=clamp(polygonPoint,0,points.length-1);const point=points[polygonPoint],node=nodeById(selected),animated=!!node.animation?.points;
      return `<div class="inspector-section node-polygon-editor"><div class="control-row"><label>Polygon path · frame ${currentFrame()}</label>${keyButton(node,'points')}</div><svg data-polygon-editor viewBox="0 0 256 256" tabindex="0" role="group" aria-label="Editable polygon mask vertices" style="${editorStyle}">${polygonGraphic(points)}</svg><p class="note">${animated?'Drag a vertex to key this shape at the playhead. Vertex count stays fixed across keys.':'Drag a vertex. Double-click an edge to add one.'} Placement, size and rotation apply to the whole shape.</p><div class="field-row"><label>Vertex X<input data-polygon-coordinate="0" type="number" min="0" max="1" step=".001" value="${point[0]}"></label><label>Vertex Y<input data-polygon-coordinate="1" type="number" min="0" max="1" step=".001" value="${point[1]}"></label></div><div class="inspector-actions"><button data-node-action="polygon-add" ${points.length>=24||animated?'disabled':''}>Add vertex</button><button data-node-action="polygon-remove" ${points.length<=3||animated?'disabled':''}>Remove vertex</button></div><button data-node-action="polygon-reset" class="quiet full" ${animated?'disabled':''}>Reset polygon</button></div>`;
    }
    function renderInspector(element=inspector) {
      if(element!==inspector){if(inspector){inspector.removeEventListener('input',inspectorInput);inspector.removeEventListener('change',inspectorChange);inspector.removeEventListener('click',inspectorClick);inspector.removeEventListener('keydown',onKey);inspector.removeEventListener('pointerdown',inspectorPointerDown);inspector.removeEventListener('dblclick',inspectorDoubleClick);}inspector=element;if(inspector){inspector.addEventListener('input',inspectorInput);inspector.addEventListener('change',inspectorChange);inspector.addEventListener('click',inspectorClick);inspector.addEventListener('keydown',onKey);inspector.addEventListener('pointerdown',inspectorPointerDown);inspector.addEventListener('dblclick',inspectorDoubleClick);}}
      if(!inspector)return;
      const node=nodeById(selected);if(!context.key||!node){inspector.innerHTML='<p class="note">Select a picture clip to edit its image graph.</p>';return;}
      const definition=definitions[node.type],p=paramsAt(node,currentFrame()),output=node.id===graph.output;
      inspector.innerHTML=`<div class="node-inspector-heading"><span style="background:${definition.color}"></span><strong>${escape(label(node))}</strong>${output?'<small>OUTPUT</small>':''}</div><p class="note">${escape(definition.description)}</p>${node.type==='source'?`<div class="node-source-info">${context.sourceThumb?`<img src="${escape(context.sourceThumb)}" alt="Selected source">`:''}<strong>${escape(context.sourceLabel||'Selected clip')}</strong><span>The graph processes this clip. Clip transforms and timeline layers are applied afterward.</span></div>`:''}${node.inputs.length?`<div class="inspector-section"><h3>CONNECTIONS</h3>${node.inputs.map((id,index)=>`<label>${definition.inputs[index]}<select data-node-connection="${index}" aria-label="${definition.inputs[index]} connection">${graph.nodes.filter(item=>!wouldCycle(graph,item.id,node.id)).map(item=>`<option value="${escape(item.id)}" ${id===item.id?'selected':''}>${escape(label(item))}</option>`).join('')}</select></label>`).join('')}</div>`:''}${node.type==='chroma_key'?`<div class="color-control"><label>Remove color</label><input type="color" data-node-param="color" value="${escape(p.color)}" aria-label="Chroma key color"></div>`:''}${node.type==='curves'?curveEditor(p):''}${node.type==='mask'?`<div class="inspector-section"><label>Shape<select data-node-param="shape"><option value="ellipse" ${p.shape==='ellipse'?'selected':''}>Ellipse</option><option value="rectangle" ${p.shape==='rectangle'?'selected':''}>Rectangle</option><option value="polygon" ${p.shape==='polygon'?'selected':''}>Polygon</option></select></label></div>${p.shape==='polygon'?polygonEditor(p):''}`:''}${node.type==='merge'?`<div class="inspector-section"><label>Blend mode<select data-node-param="mode" aria-label="Merge blend mode">${Object.entries(BLEND_MODES).map(([value,name])=>`<option value="${value}" ${p.mode===value?'selected':''}>${name}</option>`).join('')}</select></label></div>`:''}${(definition.fields||[]).map(([name,title,min,max,step])=>parameterControl(name,title,min,max,step,number(p[name],definition.defaults[name]))).join('')}${node.type==='mask'?`<label class="check-field"><input type="checkbox" data-node-param="invert" ${p.invert?'checked':''}> Invert mask</label>`:''}${animationEditor(node)}<div class="inspector-actions"><button data-node-action="output" ${output?'disabled':''}>Use as output</button>${node.type!=='source'?'<button data-node-action="duplicate">Duplicate</button>':''}</div>${node.type!=='source'?'<button class="quiet full node-delete" data-node-action="delete">Delete node · reconnect its inputs</button>':''}<p class="note node-render-note">Frame preview and export evaluate the connected graph. Clip placement is applied afterward.</p>`;
    }
    function editorPoints(next,kind,channel=curveChannel,nodeId=selected) {
      const target=next.nodes.find(node=>node.id===nodeId);target.params??={};
      const key=kind==='curve'?channel:'points';
      target.params[key]??=copy(kind==='curve'?IDENTITY:POLYGON);
      if(kind==='polygon'&&target.animation?.points){
        const keys=target.animation.points,existing=keys.find(key=>key.frame===currentFrame());
        if(existing)return existing.value;
        const value=paramsAt(target,currentFrame()).points;
        keys.push({frame:currentFrame(),value,interpolation:'linear'});keys.sort((a,b)=>a.frame-b.frame);
        return value;
      }
      return target.params[key];
    }
    function editorPosition(event,svg,kind) {
      const rect=svg.getBoundingClientRect(),x=(event.clientX-rect.left)*256/rect.width,y=(event.clientY-rect.top)*256/rect.height;
      return [clamp((x-18)/220,0,1),clamp((kind==='curve'?238-y:y-18)/220,0,1)];
    }
    function updateEditorGraphic(edit) {
      const points=editorPoints(edit.next,edit.kind,edit.channel,edit.nodeId),point=points[edit.index];
      edit.svg.innerHTML=edit.kind==='curve'?curveGraphic(points):polygonGraphic(points);
      inspector?.querySelectorAll(`[data-${edit.kind==='curve'?'curve':'polygon'}-coordinate]`).forEach(input=>{const axis=Number(input.dataset[edit.kind==='curve'?'curveCoordinate':'polygonCoordinate']);input.value=point[axis];});
    }
    function inspectorPointerDown(event) {
      if(event.button!==0||event.isPrimary===false||!context.key)return;
      const svg=event.target.closest('[data-curve-editor],[data-polygon-editor]');if(!svg)return;
      const kind=svg.hasAttribute('data-curve-editor')?'curve':'polygon';if(kind==='polygon'&&!canEditPath())return;
      const next=copy(graph),points=editorPoints(next,kind),handle=event.target.closest(`[data-${kind}-point]`);
      let index=handle?Number(handle.dataset[kind==='curve'?'curvePoint':'polygonPoint']):-1,inserted=false;
      if(index<0&&kind==='curve'){
        const point=editorPosition(event,svg,kind);index=points.findIndex(existing=>Math.abs(existing[0]-point[0])<POINT_GAP);
        if(index<0){if(points.length>=12){notify('A channel supports up to 12 curve points.');return;}index=points.findIndex(existing=>existing[0]>point[0]);if(index<1)index=points.length-1;points.splice(index,0,point);inserted=true;}
      }
      event.preventDefault();event.stopPropagation();svg.focus({preventScroll:true});
      if(index<0)return;
      if(kind==='curve')curvePoint=index;else polygonPoint=index;
      editorDrag={kind,next,index,inserted,changed:inserted,svg,nodeId:selected,channel:curveChannel,key:context.key,pointerId:event.pointerId};
      try{svg.setPointerCapture?.(event.pointerId);}catch(_){}updateEditorGraphic(editorDrag);
    }
    function editorPointerMove(event) {
      const edit=editorDrag;if(!edit||event.pointerId!==edit.pointerId)return;
      const points=editorPoints(edit.next,edit.kind,edit.channel,edit.nodeId),point=editorPosition(event,edit.svg,edit.kind);
      if(edit.kind==='curve')point[0]=edit.index===0?0:edit.index===points.length-1?1:clamp(point[0],points[edit.index-1][0]+POINT_GAP,points[edit.index+1][0]-POINT_GAP);
      const rounded=point.map(value=>Math.round(value*1e6)/1e6);
      if(rounded[0]!==points[edit.index][0]||rounded[1]!==points[edit.index][1])edit.changed=true;
      points[edit.index]=rounded;updateEditorGraphic(edit);event.preventDefault();
    }
    function finishEditor(cancel=false) {
      const edit=editorDrag;if(!edit)return;editorDrag=null;
      try{if(edit.svg.hasPointerCapture?.(edit.pointerId))edit.svg.releasePointerCapture(edit.pointerId);}catch(_){}
      if(!cancel&&edit.changed&&edit.key===context.key&&edit.nodeId===selected&&!destroyed){if(!commit(edit.next))renderInspector();}
      else renderInspector();
    }
    function insertPolygon(next,index,point) {
      if(nodeById(selected)?.animation?.points){notify('Make the polygon path static before changing its vertex count.',true);return;}
      const points=editorPoints(next,'polygon');if(points.length>=24){notify('A mask supports up to 24 vertices.');return;}
      points.splice(index+1,0,point);polygonPoint=index+1;commit(next);
    }
    function inspectorDoubleClick(event) {
      const svg=event.target.closest('[data-polygon-editor]');if(!svg||event.target.closest('[data-polygon-point]'))return;
      event.preventDefault();event.stopPropagation();const next=copy(graph),points=editorPoints(next,'polygon'),point=editorPosition(event,svg,'polygon');let best=null;
      for(let i=0;i<points.length;i++){const a=points[i],b=points[(i+1)%points.length],dx=b[0]-a[0],dy=b[1]-a[1],t=clamp(((point[0]-a[0])*dx+(point[1]-a[1])*dy)/(dx*dx+dy*dy),.05,.95),projected=[a[0]+t*dx,a[1]+t*dy],distance=Math.hypot(point[0]-projected[0],point[1]-projected[1]);if(!best||distance<best.distance)best={index:i,point:projected,distance};}
      if(best?.distance<.07)insertPolygon(next,best.index,best.point);
    }
    function editPointAction(action) {
      const node=nodeById(selected);if(!node)return;
      if(action.startsWith('curve-')&&node.type==='curves'){
        const next=copy(graph),points=editorPoints(next,'curve');
        if(action==='curve-reset'){next.nodes.find(item=>item.id===selected).params[curveChannel]=copy(IDENTITY);curvePoint=0;commit(next);}
        else if(action==='curve-remove'&&curvePoint>0&&curvePoint<points.length-1){points.splice(curvePoint,1);curvePoint=Math.max(0,curvePoint-1);commit(next);}
      }
      if(action.startsWith('polygon-')&&node.type==='mask'){
        if(node.animation?.points){notify('Make the polygon path static before changing its vertex count.',true);return;}
        const next=copy(graph),points=editorPoints(next,'polygon');
        if(action==='polygon-reset'){next.nodes.find(item=>item.id===selected).params.points=copy(POLYGON);polygonPoint=0;commit(next);}
        else if(action==='polygon-remove'&&points.length>3){points.splice(polygonPoint,1);polygonPoint=clamp(polygonPoint,0,points.length-1);commit(next);}
        else if(action==='polygon-add'){const a=points[polygonPoint],b=points[(polygonPoint+1)%points.length];insertPolygon(next,polygonPoint,[(a[0]+b[0])/2,(a[1]+b[1])/2]);}
      }
    }
    function editorKey(event) {
      const svg=event.target.closest('[data-curve-editor],[data-polygon-editor]');if(!svg)return false;
      const kind=svg.hasAttribute('data-curve-editor')?'curve':'polygon',handle=event.target.closest(`[data-${kind}-point]`);
      if(handle){if(kind==='curve')curvePoint=Number(handle.dataset.curvePoint);else polygonPoint=Number(handle.dataset.polygonPoint);}
      if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Delete','Backspace','Escape'].includes(event.key))return true;
      event.preventDefault();event.stopPropagation();
      if(event.key==='Escape'){finishEditor(true);return true;}
      if(event.key==='Delete'||event.key==='Backspace'){editPointAction(kind+'-remove');inspector?.querySelector(`[data-${kind}-editor]`)?.focus({preventScroll:true});return true;}
      if(kind==='polygon'&&!canEditPath())return true;
      const next=copy(graph),points=editorPoints(next,kind),index=kind==='curve'?curvePoint:polygonPoint,axis=['ArrowLeft','ArrowRight'].includes(event.key)?0:1,step=event.altKey ? .001 : event.shiftKey ? .02 : .005;
      let direction=['ArrowRight','ArrowDown'].includes(event.key)?1:-1;if(kind==='curve'&&axis===1)direction*=-1;
      points[index][axis]=clamp(points[index][axis]+direction*step,0,1);
      if(kind==='curve'&&axis===0)points[index][0]=index===0?0:index===points.length-1?1:clamp(points[index][0],points[index-1][0]+POINT_GAP,points[index+1][0]-POINT_GAP);
      if(commit(next))inspector?.querySelector(`[data-${kind}-point="${index}"]`)?.focus({preventScroll:true});
      return true;
    }
    function inspectorInput(event) {
      const input=event.target;if(!input.dataset.nodeParam||!['range','number'].includes(input.type))return;
      for(const control of inspector.querySelectorAll('[data-node-param]'))if(control!==input&&control.dataset.nodeParam===input.dataset.nodeParam)control.value=input.value;
    }
    function inspectorChange(event) {
      const input=event.target,node=nodeById(selected);if(!node)return;
      if(input.hasAttribute('data-node-animation-channel')){if(animationFields(node.type).includes(input.value)){animationChannel=input.value;renderInspector();}return;}
      if(input.hasAttribute('data-node-animation-frame')){seekAnimation(Number(input.value));return;}
      if(input.hasAttribute('data-node-animation-easing')){
        if(!Object.hasOwn(EASING,input.value))return;
        const next=copy(graph),key=next.nodes.find(item=>item.id===selected).animation?.[animationChannel]?.find(key=>key.frame===currentFrame());
        if(key){key.interpolation=input.value;commit(next);}return;
      }
      if(input.hasAttribute('data-node-key-time')){
        const frame=Number(input.value),next=copy(graph),keys=next.nodes.find(item=>item.id===selected).animation?.[animationChannel],key=keys?.find(key=>key.frame===currentFrame());
        if(!key)return;if(!Number.isInteger(frame)||!frameAllowed(frame)||keys.some(item=>item!==key&&item.frame===frame)){notify('Choose an unoccupied integer frame inside the animation domain.',true);renderInspector();return;}
        key.frame=frame;keys.sort((a,b)=>a.frame-b.frame);if(commit(next))seekAnimation(frame);return;
      }
      if(input.hasAttribute('data-curve-channel')){if(CURVE_CHANNELS.includes(input.value)){curveChannel=input.value;curvePoint=0;renderInspector();}return;}
      if(input.dataset.curveCoordinate!==undefined||input.dataset.polygonCoordinate!==undefined){
        const kind=input.dataset.curveCoordinate!==undefined?'curve':'polygon',axis=Number(input.dataset[kind==='curve'?'curveCoordinate':'polygonCoordinate']),value=Number(input.value);
        if(!Number.isFinite(value)||![0,1].includes(axis)){renderInspector();return;}
        if(kind==='polygon'&&!canEditPath()){renderInspector();return;}
        const next=copy(graph),points=editorPoints(next,kind),index=kind==='curve'?curvePoint:polygonPoint;
        points[index][axis]=clamp(value,Number(input.min),Number(input.max));if(!commit(next))renderInspector();return;
      }
      if(input.dataset.nodeConnection!==undefined){connect(input.value,node.id,Number(input.dataset.nodeConnection));return;}
      const name=input.dataset.nodeParam;if(!name)return;let value=input.type==='checkbox'?input.checked:input.value;
      if(['range','number'].includes(input.type)){if(!Number.isFinite(Number(value))){renderInspector();return;}value=clamp(Number(value),Number(input.min),Number(input.max));}
      const next=copy(graph),target=next.nodes.find(n=>n.id===node.id);if(writeParameter(target,name,value))commit(next);else renderInspector();
    }
    function inspectorClick(event) {
      const keyed=event.target.closest('[data-node-key]');if(keyed){toggleKey(keyed.dataset.nodeKey);return;}
      const seek=event.target.closest('[data-node-animation-seek]');if(seek){seekAnimation(Number(seek.dataset.nodeAnimationSeek));return;}
      const remove=event.target.closest('[data-node-animation-remove]');if(remove){const next=copy(graph);if(removeAnimationKey(next,animationChannel,Number(remove.dataset.nodeAnimationRemove)))commit(next);return;}
      if(event.target.closest('[data-node-animation-clear]')){
        const node=nodeById(selected);if(!node?.animation?.[animationChannel])return;
        const value=paramsAt(node,currentFrame())[animationChannel],next=copy(graph),target=next.nodes.find(item=>item.id===selected);
        target.params??={};target.params[animationChannel]=value;delete target.animation[animationChannel];if(!Object.keys(target.animation).length)delete target.animation;commit(next);return;
      }
      const action=event.target.closest('[data-node-action]')?.dataset.nodeAction;
      if(action==='delete')deleteNode();else if(action==='duplicate')duplicateNode();else if(action==='output'){const next=copy(graph);next.output=selected;commit(next);}else if(action)editPointAction(action);
    }
    function localPoint(event) {const rect=stage.getBoundingClientRect();return {x:(event.clientX-rect.left-pan.x)/zoom,y:(event.clientY-rect.top-pan.y)/zoom};}
    function onPointerDown(event) {
      if(event.button!==0&&event.button!==1)return;
      const output=event.target.closest('[data-node-output]'),input=event.target.closest('[data-node-input]');
      if(output){event.preventDefault();pending=output.dataset.nodeOutput;selected=pending;drag={kind:'wire'};stage.focus({preventScroll:true});renderGraph();renderInspector();return;}
      if(input){event.preventDefault();if(pending)connect(pending,input.dataset.nodeTarget,Number(input.dataset.nodeInput));else selectNode(input.dataset.nodeTarget);return;}
      const nodeElement=event.target.closest('[data-node]');
      if(nodeElement){const node=nodeById(nodeElement.dataset.node);if(!node)return;event.preventDefault();selected=node.id;stage.focus({preventScroll:true});drag={kind:'node',id:node.id,start:localPoint(event),original:{...position(node)},moved:false};renderGraph();renderInspector();return;}
      if(event.target.closest('button,select,input'))return;
      event.preventDefault();stage.focus({preventScroll:true});drag={kind:'pan',x:event.clientX,y:event.clientY,original:{...pan}};stage.classList.add('panning');
    }
    function onPointerMove(event) {
      if(editorDrag){editorPointerMove(event);return;}
      if(!drag)return;
      if(drag.kind==='wire'){drawWires(localPoint(event));return;}
      if(drag.kind==='pan'){pan={x:drag.original.x+event.clientX-drag.x,y:drag.original.y+event.clientY-drag.y};applyView();return;}
      const point=localPoint(event),p={x:clamp(drag.original.x+point.x-drag.start.x,-100000,100000),y:clamp(drag.original.y+point.y-drag.start.y,-100000,100000)};if(Math.abs(p.x-drag.original.x)+Math.abs(p.y-drag.original.y)>2)drag.moved=true;positions.set(drag.id,p);
      const element=[...nodesElement.children].find(n=>n.dataset.node===drag.id);if(element){element.style.left=`${p.x}px`;element.style.top=`${p.y}px`;}drawWires();
    }
    function onPointerUp(event) {
      if(editorDrag){if(event.pointerId===editorDrag.pointerId)finishEditor();return;}
      if(!drag)return;const done=drag;drag=null;stage.classList.remove('panning');
      if(done.kind==='wire'){const input=document.elementFromPoint(event.clientX,event.clientY)?.closest('[data-node-input]');if(input&&host.contains(input))connect(pending,input.dataset.nodeTarget,Number(input.dataset.nodeInput));else renderGraph();return;}
      if(done.kind==='node'&&done.moved){const next=copy(graph);next.nodes.find(node=>node.id===done.id).position={...positions.get(done.id)};commit(next);}
    }
    function onWheel(event) {
      if(!context.key)return;event.preventDefault();
      if(event.ctrlKey||event.metaKey){const point=localPoint(event),rect=stage.getBoundingClientRect();zoom=clamp(zoom*Math.exp(-event.deltaY*.006),.2,1.8);pan={x:event.clientX-rect.left-point.x*zoom,y:event.clientY-rect.top-point.y*zoom};}
      else{pan.x-=event.deltaX;pan.y-=event.deltaY;}applyView();
    }
    function onKey(event) {
      if(event.target.matches('input,select,textarea')||event.metaKey||event.ctrlKey)return;
      if(editorKey(event))return;
      if(['Delete','Backspace'].includes(event.key)){event.preventDefault();event.stopPropagation();deleteNode();}
      if(event.key==='Escape'){event.preventDefault();event.stopPropagation();pending=null;drag=null;cachePositions();renderGraph();}
    }
    function onPointerCancel(){if(editorDrag)finishEditor(true);drag=null;pending=null;stage.classList.remove('panning');cachePositions();renderGraph();}
    function onClick(event) {const action=event.target.closest('[data-graph-action]')?.dataset.graphAction;if(action==='add')addNode(host.querySelector('[data-graph-add-type]').value);else if(action==='masked')maskedCorrection();else if(action==='fit')fit();else if(action==='preview')bridge.onRender?.();else if(action==='import')bridge.onImport?.();}
    function onChange(event) {if(event.target.matches('[data-graph-output]')){const next=copy(graph);next.output=event.target.value;commit(next);}}
    host.addEventListener('click',onClick);host.addEventListener('change',onChange);host.addEventListener('keydown',onKey);stage.addEventListener('pointerdown',onPointerDown);stage.addEventListener('wheel',onWheel,{passive:false});window.addEventListener('pointermove',onPointerMove);window.addEventListener('pointerup',onPointerUp);window.addEventListener('pointercancel',onPointerCancel);
    const resize = new ResizeObserver(()=>{if(!destroyed&&context.key)fit();});resize.observe(stage);
    cachePositions();renderGraph();
    return {
      setContext(next) {const different=context.key!==next.key;context=next;graph=copy(next.graph||freshGraph());if(validate(graph,context)){notify(validate(graph,context),true);}if(different||!nodeById(selected))selected=graph.output;pending=null;drag=null;editorDrag=null;if(different){curveChannel='master';curvePoint=0;polygonPoint=0;animationChannel=null;}cachePositions();renderGraph();renderInspector();if(different)requestAnimationFrame(fit);},
      setFrame(frame){if(!Number.isFinite(frame)||Math.round(frame)===currentFrame())return;if(editorDrag)finishEditor(true);context={...context,frame:Math.round(frame)};renderInspector();},
      renderInspector,
      refresh(){renderGraph();renderInspector();},
      fit,
      destroy(){destroyed=true;editorDrag=null;resize.disconnect();host.removeEventListener('click',onClick);host.removeEventListener('change',onChange);host.removeEventListener('keydown',onKey);stage.removeEventListener('pointerdown',onPointerDown);stage.removeEventListener('wheel',onWheel);window.removeEventListener('pointermove',onPointerMove);window.removeEventListener('pointerup',onPointerUp);window.removeEventListener('pointercancel',onPointerCancel);if(inspector){inspector.removeEventListener('input',inspectorInput);inspector.removeEventListener('change',inspectorChange);inspector.removeEventListener('click',inspectorClick);inspector.removeEventListener('keydown',onKey);inspector.removeEventListener('pointerdown',inspectorPointerDown);inspector.removeEventListener('dblclick',inspectorDoubleClick);}host.innerHTML='';}
    };
  }
  window.CinematicumCompositor = {mount,validate,wouldCycle,defaultGraph:freshGraph,nodeTypes:copy(definitions),curveValue,animationValue,paramsAt,animationFields};
})();
