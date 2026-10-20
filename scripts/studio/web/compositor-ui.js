/* Editable FFmpeg image graph. No source pixels are fabricated in this workspace. */
(() => {
  'use strict';
  const copy = value => JSON.parse(JSON.stringify(value));
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const number = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
  const definitions = {
    source: {name:'Source',inputs:[],color:'#6d9fac',defaults:{},description:'The selected clip, trimmed and fitted to the project canvas. Every branch starts with this image.'},
    grade: {name:'Color grade',inputs:['Image'],color:'#bc9bd3',defaults:{exposure:0,contrast:1,saturation:1,temperature:0},description:'Correct this branch before combining it with other branches.',fields:[['exposure','Exposure · stops',-3,3,.05],['contrast','Contrast',0,3,.05],['saturation','Saturation',0,3,.05],['temperature','Temperature',-1,1,.02]]},
    blur: {name:'Gaussian blur',inputs:['Image'],color:'#82a4ce',defaults:{sigma:2},description:'Blur the image and its alpha with a Gaussian filter.',fields:[['sigma','Radius',0,30,.1]]},
    sharpen: {name:'Sharpen',inputs:['Image'],color:'#82a4ce',defaults:{amount:1},description:'Recover edge definition with an unsharp mask.',fields:[['amount','Amount',0,3,.05]]},
    chroma_key: {name:'Chroma key',inputs:['Image'],color:'#80b99b',defaults:{color:'#00ff00',similarity:.18,blend:.08},description:'Remove a selected color. Connect the transparent result to a Merge foreground.',fields:[['similarity','Color similarity',.01,1,.01],['blend','Edge blend',0,1,.01]]},
    mask: {name:'Shape mask',inputs:['Image'],color:'#cfad76',defaults:{shape:'ellipse',x:.5,y:.5,width:.65,height:.65,feather:.15,invert:false},description:'Multiply this branch’s alpha by an ellipse or rectangle. Positions and dimensions are normalized to the image.',fields:[['x','Center X',0,1,.01],['y','Center Y',0,1,.01],['width','Width',.01,2,.01],['height','Height',.01,2,.01],['feather','Inward feather',0,1,.01]]},
    merge: {name:'Merge',inputs:['Background','Foreground'],color:'#d39c84',defaults:{opacity:1},description:'Composite the foreground over the background using its alpha and this opacity.',fields:[['opacity','Foreground opacity',0,1,.01]]}
  };
  const NODE_WIDTH = 174;
  const nodeHeight = node => node.type === 'source' ? 132 : node.type === 'merge' ? 120 : 110;
  const freshGraph = () => ({version:1,nodes:[{id:'source',type:'source',inputs:[],params:{},position:{x:42,y:62}}],output:'source'});
  function validate(graph) {
    if (!graph || graph.version !== 1 || !Array.isArray(graph.nodes) || !graph.nodes.length || graph.nodes.length > 32) return 'A graph needs 1–32 nodes and version 1.';
    const nodes = new Map();
    for (const node of graph.nodes) {
      if (!node || typeof node.id !== 'string' || !node.id || nodes.has(node.id)) return 'Every node needs a unique ID.';
      if (!definitions[node.type]) return 'This graph contains an unsupported node.';
      if (!Array.isArray(node.inputs) || node.inputs.length !== definitions[node.type].inputs.length) return `${definitions[node.type].name} has the wrong number of inputs.`;
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
  function wouldCycle(graph, from, to) {
    const nodes = new Map(graph.nodes.map(node => [node.id,node])), seen = new Set();
    function contains(id) {
      if (id === to) return true;
      if (seen.has(id)) return false;
      seen.add(id);return (nodes.get(id)?.inputs || []).some(contains);
    }
    return contains(from);
  }
  function mount(host, bridge = {}) {
    let graph = freshGraph(), context = {}, selected = 'source', inspector = null, pending = null, drag = null;
    let zoom = 1, pan = {x:0,y:0}, destroyed = false, positions = new Map();
    host.classList.add('compositor-editor');
    host.innerHTML = `<div class="compositor-toolbar"><span class="compositor-title">NODE COMPOSITOR</span><select data-graph-add-type aria-label="Node type to add">${Object.entries(definitions).filter(([type])=>type!=='source').map(([type,definition])=>`<option value="${type}">${definition.name}</option>`).join('')}</select><button data-graph-action="add" class="small" title="Add after the selected node">＋ Add</button><button data-graph-action="masked" class="quiet small" title="Create a grade, feathered mask, and merge branch">Masked correction</button><span class="compositor-toolbar-spacer"></span><button data-graph-action="fit" class="quiet small" title="Fit all nodes">Fit</button><button data-graph-action="preview" class="small">Render preview ↗</button></div><div class="compositor-stage" tabindex="0" aria-label="Node graph. Drag nodes, or connect an output port to an input port."><div class="compositor-world"><svg class="compositor-wires" aria-hidden="true"></svg><div class="compositor-nodes"></div></div><div class="compositor-empty" hidden><strong>Select a picture clip.</strong><span>Import a video or image, add it to the timeline, then select its clip.</span><button data-graph-action="import" class="small">Import media</button></div><div class="compositor-connection-hint" hidden></div></div><div class="compositor-footer"><span data-graph-status>Source → output</span><span>Drag background to pan · ⌘/Ctrl + wheel to zoom</span><label>Output <select data-graph-output aria-label="Compositor output node"></select></label></div>`;
    const stage=host.querySelector('.compositor-stage'),world=host.querySelector('.compositor-world'),nodesElement=host.querySelector('.compositor-nodes'),wires=host.querySelector('.compositor-wires');
    const notify = (message,error=false) => bridge.toast?.(message,error);
    const nodeById = id => graph.nodes.find(node => node.id===id);
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
      if(node.type==='blur')return `Radius ${number(p.sigma).toFixed(1)}`;
      if(node.type==='sharpen')return `Amount ${number(p.amount).toFixed(2)}`;
      if(node.type==='chroma_key')return `${p.color} · ${number(p.similarity).toFixed(2)}`;
      if(node.type==='mask')return `${p.shape}${p.invert?' · inverted':''} · feather ${number(p.feather).toFixed(2)}`;
      return `Foreground ${Math.round(number(p.opacity,1)*100)}%`;
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
      const error=validate(next);if(error){notify(error,true);return false;}
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
    function parameterControl(name,title,min,max,step,value) {return `<div class="node-parameter"><div><label>${escape(title)}</label><input type="number" data-node-param="${name}" min="${min}" max="${max}" step="${step}" value="${value}" aria-label="${escape(title)}"></div><input type="range" data-node-param="${name}" min="${min}" max="${max}" step="${step}" value="${value}" aria-label="${escape(title)} slider"></div>`;}
    function renderInspector(element=inspector) {
      if(element!==inspector){if(inspector){inspector.removeEventListener('input',inspectorInput);inspector.removeEventListener('change',inspectorChange);inspector.removeEventListener('click',inspectorClick);inspector.removeEventListener('keydown',onKey);}inspector=element;if(inspector){inspector.addEventListener('input',inspectorInput);inspector.addEventListener('change',inspectorChange);inspector.addEventListener('click',inspectorClick);inspector.addEventListener('keydown',onKey);}}
      if(!inspector)return;
      const node=nodeById(selected);if(!context.key||!node){inspector.innerHTML='<p class="note">Select a picture clip to edit its image graph.</p>';return;}
      const definition=definitions[node.type],p={...definition.defaults,...node.params},output=node.id===graph.output;
      inspector.innerHTML=`<div class="node-inspector-heading"><span style="background:${definition.color}"></span><strong>${escape(label(node))}</strong>${output?'<small>OUTPUT</small>':''}</div><p class="note">${escape(definition.description)}</p>${node.type==='source'?`<div class="node-source-info">${context.sourceThumb?`<img src="${escape(context.sourceThumb)}" alt="Selected source">`:''}<strong>${escape(context.sourceLabel||'Selected clip')}</strong><span>The graph processes this clip. Clip transforms and timeline layers are applied afterward.</span></div>`:''}${node.inputs.length?`<div class="inspector-section"><h3>CONNECTIONS</h3>${node.inputs.map((id,index)=>`<label>${definition.inputs[index]}<select data-node-connection="${index}" aria-label="${definition.inputs[index]} connection">${graph.nodes.filter(item=>!wouldCycle(graph,item.id,node.id)).map(item=>`<option value="${escape(item.id)}" ${id===item.id?'selected':''}>${escape(label(item))}</option>`).join('')}</select></label>`).join('')}</div>`:''}${node.type==='chroma_key'?`<div class="color-control"><label>Remove color</label><input type="color" data-node-param="color" value="${escape(p.color)}" aria-label="Chroma key color"></div>`:''}${node.type==='mask'?`<div class="inspector-section"><label>Shape<select data-node-param="shape"><option value="ellipse" ${p.shape==='ellipse'?'selected':''}>Ellipse</option><option value="rectangle" ${p.shape==='rectangle'?'selected':''}>Rectangle</option></select></label></div>`:''}${(definition.fields||[]).map(([name,title,min,max,step])=>parameterControl(name,title,min,max,step,number(p[name],definition.defaults[name]))).join('')}${node.type==='mask'?`<label class="check-field"><input type="checkbox" data-node-param="invert" ${p.invert?'checked':''}> Invert mask</label>`:''}<div class="inspector-actions"><button data-node-action="output" ${output?'disabled':''}>Use as output</button>${node.type!=='source'?'<button data-node-action="duplicate">Duplicate</button>':''}</div>${node.type!=='source'?'<button class="quiet full node-delete" data-node-action="delete">Delete node · reconnect its inputs</button>':''}<p class="note node-render-note">Render preview evaluates this graph. Source preview shows the original clip with its clip-level controls.</p>`;
    }
    function inspectorInput(event) {
      const input=event.target;if(!input.dataset.nodeParam||!['range','number'].includes(input.type))return;
      for(const control of inspector.querySelectorAll('[data-node-param]'))if(control!==input&&control.dataset.nodeParam===input.dataset.nodeParam)control.value=input.value;
    }
    function inspectorChange(event) {
      const input=event.target,node=nodeById(selected);if(!node)return;
      if(input.dataset.nodeConnection!==undefined){connect(input.value,node.id,Number(input.dataset.nodeConnection));return;}
      const name=input.dataset.nodeParam;if(!name)return;let value=input.type==='checkbox'?input.checked:input.value;
      if(['range','number'].includes(input.type)){if(!Number.isFinite(Number(value))){renderInspector();return;}value=clamp(Number(value),Number(input.min),Number(input.max));}
      const next=copy(graph),target=next.nodes.find(n=>n.id===node.id);target.params??={};target.params[name]=value;commit(next);
    }
    function inspectorClick(event) {const action=event.target.closest('[data-node-action]')?.dataset.nodeAction;if(action==='delete')deleteNode();else if(action==='duplicate')duplicateNode();else if(action==='output'){const next=copy(graph);next.output=selected;commit(next);}}
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
      if(!drag)return;
      if(drag.kind==='wire'){drawWires(localPoint(event));return;}
      if(drag.kind==='pan'){pan={x:drag.original.x+event.clientX-drag.x,y:drag.original.y+event.clientY-drag.y};applyView();return;}
      const point=localPoint(event),p={x:clamp(drag.original.x+point.x-drag.start.x,-100000,100000),y:clamp(drag.original.y+point.y-drag.start.y,-100000,100000)};if(Math.abs(p.x-drag.original.x)+Math.abs(p.y-drag.original.y)>2)drag.moved=true;positions.set(drag.id,p);
      const element=[...nodesElement.children].find(n=>n.dataset.node===drag.id);if(element){element.style.left=`${p.x}px`;element.style.top=`${p.y}px`;}drawWires();
    }
    function onPointerUp(event) {
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
      if(['Delete','Backspace'].includes(event.key)){event.preventDefault();event.stopPropagation();deleteNode();}
      if(event.key==='Escape'){event.preventDefault();event.stopPropagation();pending=null;drag=null;cachePositions();renderGraph();}
    }
    function onClick(event) {const action=event.target.closest('[data-graph-action]')?.dataset.graphAction;if(action==='add')addNode(host.querySelector('[data-graph-add-type]').value);else if(action==='masked')maskedCorrection();else if(action==='fit')fit();else if(action==='preview')bridge.onRender?.();else if(action==='import')bridge.onImport?.();}
    function onChange(event) {if(event.target.matches('[data-graph-output]')){const next=copy(graph);next.output=event.target.value;commit(next);}}
    host.addEventListener('click',onClick);host.addEventListener('change',onChange);host.addEventListener('keydown',onKey);stage.addEventListener('pointerdown',onPointerDown);stage.addEventListener('wheel',onWheel,{passive:false});window.addEventListener('pointermove',onPointerMove);window.addEventListener('pointerup',onPointerUp);
    const resize = new ResizeObserver(()=>{if(!destroyed&&context.key)fit();});resize.observe(stage);
    cachePositions();renderGraph();
    return {
      setContext(next) {const different=context.key!==next.key;context=next;graph=copy(next.graph||freshGraph());if(validate(graph)){notify(validate(graph),true);}if(different||!nodeById(selected))selected=graph.output;pending=null;drag=null;cachePositions();renderGraph();renderInspector();if(different)requestAnimationFrame(fit);},
      renderInspector,
      refresh(){renderGraph();renderInspector();},
      fit,
      destroy(){destroyed=true;resize.disconnect();host.removeEventListener('click',onClick);host.removeEventListener('change',onChange);host.removeEventListener('keydown',onKey);stage.removeEventListener('pointerdown',onPointerDown);stage.removeEventListener('wheel',onWheel);window.removeEventListener('pointermove',onPointerMove);window.removeEventListener('pointerup',onPointerUp);if(inspector){inspector.removeEventListener('input',inspectorInput);inspector.removeEventListener('change',inspectorChange);inspector.removeEventListener('click',inspectorClick);inspector.removeEventListener('keydown',onKey);}host.innerHTML='';}
    };
  }
  window.CinematicumCompositor = {mount,validate,wouldCycle,defaultGraph:freshGraph,nodeTypes:copy(definitions)};
})();
