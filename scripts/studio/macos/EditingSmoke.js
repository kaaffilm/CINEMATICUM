// Async-function body for SmokeTest.swift --script. Synthetic ENGINE TEST media.
// Drives shipped DOM controls in real WKWebView; never touches application state
// or sends HTTP requests. The Python fixture independently inspects disk output.
return await (async () => {
  const began=performance.now(),deadline=began+12600,steps=[],timings={};
  const $=selector=>document.querySelector(selector);
  const all=selector=>[...document.querySelectorAll(selector)];
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const profile=new URLSearchParams(location.search).get('smoke_profile')==='preview'?'preview':'h264';
  const result={profile};
  const diagnostics=()=>'; toast='+($('#toast')?.textContent||'')+'; frame='+($('#frame-status')?.textContent||'')+'; job='+($('#job-label')?.textContent||'')+' / '+($('#job-detail')?.textContent||'');
  function require(condition,message){if(!condition)throw Error(message+diagnostics());}
  function mark(name){steps.push(name);timings[name]=Math.round(performance.now()-began);}
  async function until(predicate,label,milliseconds=1600){
    const end=Math.min(deadline,performance.now()+milliseconds);
    while(performance.now()<end){if(predicate())return;await sleep(35);}
    throw Error(label+diagnostics());
  }
  function control(selector){
    const element=$(selector);
    require(element&&!element.disabled&&!element.closest('[inert]'),'Unavailable control: '+selector);
    element.scrollIntoView({block:'nearest',inline:'nearest'});
    return element;
  }
  function click(selector){control(selector).click();}
  function set(selector,value){
    const element=control(selector);
    if(element.type==='checkbox')element.checked=Boolean(value);else element.value=String(value);
    if(element.type==='range')element.dispatchEvent(new Event('input',{bubbles:true}));
    element.dispatchEvent(new Event('change',{bubbles:true}));
  }
  function field(name,value){set('[data-field="'+name+'"]',value);}
  function openPlacement(){if(!$('.clip-transform-details')?.open)click('.clip-transform-details summary');}
  function pointer(target,type,x,y){
    target.dispatchEvent(new PointerEvent(type,{bubbles:true,cancelable:true,pointerId:73,pointerType:'mouse',isPrimary:true,button:0,buttons:type==='pointerup'?0:1,clientX:x,clientY:y}));
  }
  function editorPoint(svg,kind,x,y){
    const r=svg.getBoundingClientRect();require(r.width>40&&r.height>40,'Point editor has no drawing area');
    return {x:r.left+(18+220*x)/256*r.width,y:r.top+(kind==='curve'?238-220*y:18+220*y)/256*r.height};
  }
  function dragPoint(kind,index,from,to){
    const svg=control('[data-'+kind+'-editor]'),start=editorPoint(svg,kind,...from),end=editorPoint(svg,kind,...to);
    const target=index===null?svg:svg.querySelector('[data-'+kind+'-point="'+index+'"]');
    require(target,'Missing editable point handle');
    pointer(target,'pointerdown',start.x,start.y);
    pointer(window,'pointermove',(start.x+end.x)/2,(start.y+end.y)/2);
    pointer(window,'pointermove',end.x,end.y);
    pointer(window,'pointerup',end.x,end.y);
  }
  function choosePoint(kind,index){
    const handle=control('[data-'+kind+'-point="'+index+'"]'),r=handle.getBoundingClientRect();
    pointer(handle,'pointerdown',r.left+r.width/2,r.top+r.height/2);
    pointer(window,'pointerup',r.left+r.width/2,r.top+r.height/2);
  }
  function canvasEvidence(canvas){
    const context=canvas.getContext('2d',{willReadFrequently:true}),pixels=context.getImageData(0,0,canvas.width,canvas.height).data;
    let hash=2166136261,ink=0;const colors=new Set();
    for(let i=0;i<pixels.length;i+=4){
      const r=pixels[i],g=pixels[i+1],b=pixels[i+2];
      hash=Math.imul(hash^r,16777619);hash=Math.imul(hash^g,16777619);hash=Math.imul(hash^b,16777619);
      const background=Math.abs(r-13)+Math.abs(g-17)+Math.abs(b-23)<7;
      const grid=Math.abs(r-41)+Math.abs(g-51)+Math.abs(b-62)<7;
      if(!background&&!grid)ink++;
      if(i%28===0)colors.add((r>>3)+','+(g>>3)+','+(b>>3));
    }
    return {width:canvas.width,height:canvas.height,hash:(hash>>>0).toString(16),ink_pixels:ink,unique_colors:colors.size};
  }
  async function exactFrame(){
    await until(()=>!$('#processed-frame')?.hidden&&$('#processed-frame').complete&&$('#processed-frame').naturalWidth===160&&$('#frame-status')?.textContent==='Rendered frame 3 · export graph','Exact paused frame 3 did not arrive',3800);
    const image=$('#processed-frame'),url=new URL(image.currentSrc||image.src,location.href);
    require(url.origin===location.origin&&/\/previews\/[a-f0-9]{64}\.png$/.test(url.pathname),'Paused frame did not come from the project PNG renderer');
    const sample=document.createElement('canvas');sample.width=image.naturalWidth;sample.height=image.naturalHeight;sample.getContext('2d').drawImage(image,0,0);
    const evidence=canvasEvidence(sample);require(evidence.unique_colors>12,'The paused picture is uniform or empty');
    return {...evidence,url:url.pathname,frame:3,status:$('#frame-status').textContent};
  }
  try {
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST')&&$('.media-item[data-asset] [data-add]')&&!$('#export-button').disabled,'Isolated source project did not bootstrap',4200);
    require(all('.timeline-clip[data-type="clip"]').length===0,'Fixture timeline was not empty');
    result.project_id=$('#project-select').value;result.asset_id=$('.media-item[data-asset]').dataset.asset;
    click('.media-item[data-asset] [data-add]');
    require(all('.timeline-clip[data-type="clip"]').length===1,'Media add did not create one clip');
    result.clip_id=$('.timeline-clip[data-type="clip"]').dataset.clip;
    click('#jump-end');require($('#timecode').textContent==='00:00:01:11','Source fixture must contain 24 project frames');
    field('duration',12);
    require($('#timecode').textContent==='00:00:00:11','Shortening the timeline did not clamp the playhead');
    field('in',.5);field('speed',1.5);field('reverse',true);
    require(Number($('[data-field="in"]').value)===.5&&Number($('[data-field="duration"]').value)===8,'Retime lost the fractional source in or source range');
    require($('#timecode').textContent==='00:00:00:07','Retime did not clamp the playhead to the new end');
    field('volume',.8);field('audio.pan',.25);field('audio.fade_in',1);field('audio.fade_out',1);
    mark('source_add_fractional_retime_reverse_and_playhead_clamp');

    for(const key of ['mute','solo','locked']){
      click('[data-track-control="'+key+'"][data-track-id="0"]');
      require($('[data-track-control="'+key+'"][data-track-id="0"]').getAttribute('aria-pressed')==='true','Track '+key+' did not enable');
      if(key==='mute')require($('.track-row[data-track="0"]').classList.contains('muted-track'),'Muted track did not reflect its state');
      if(key==='locked'){
        require($('.track-row[data-track="0"]').classList.contains('locked-track'),'Track did not lock');
        const duration=$('[data-field="duration"]');
        if(!duration.disabled)field('duration',4);
        click('[data-mode="audio"]');click('[data-mode="edit"]');
        require(Number($('[data-field="duration"]').value)===8,'A locked clip accepted a duration edit');
      }
      if(key!=='solo'){
        click('[data-track-control="'+key+'"][data-track-id="0"]');
        require($('[data-track-control="'+key+'"][data-track-id="0"]').getAttribute('aria-pressed')==='false','Track '+key+' did not disable');
      }
    }
    click('[data-mode="audio"]');set('[data-track-name="0"]','ENGINE TEST picture');set('[data-track-gain="0"]',.65);
    require(Number($('[data-track-gain="0"]').value)===.65,'Mixer gain did not update');
    require($('[data-mixer-toggle="solo"][data-track-id="0"]').getAttribute('aria-pressed')==='true','Timeline solo did not reach the mixer');
    mark('track_mute_solo_lock_guard_and_mixer_gain');

    click('[data-mode="composite"]');click('#jump-start');openPlacement();click('[data-action="keyframe"]');
    openPlacement();require($('[data-key-easing="0"]').value==='linear','New transform key was not linear');
    set('[data-key-easing="0"]','ease_in_out');click('#undo-button');openPlacement();
    require($('[data-key-easing="0"]')?.value==='linear','Undo did not restore keyframe interpolation');
    click('#redo-button');openPlacement();require($('[data-key-easing="0"]')?.value==='ease_in_out','Redo did not restore easing');
    click('#jump-end');openPlacement();field('x',.12);
    click('[data-mode="edit"]');click('[data-mode="composite"]');openPlacement();
    require($('[data-key-easing="7"]')&&all('.keyframe-chip').length===2,'Changing pose at the end did not write a second key');
    click('#jump-start');for(let i=0;i<3;i++)click('#step-forward');
    require($('#timecode').textContent==='00:00:00:03','Could not select paused frame 3');
    mark('transform_keys_outgoing_easing_undo_redo');

    set('[data-graph-add-type]','curves');click('[data-graph-action="add"]');
    result.curves_id=$('[data-graph-output]').value;
    dragPoint('curve',null,[.4,.4],[.4,.7]);
    require(all('[data-curve-point]').length===3,'Curve drag did not create a midpoint');
    click('#undo-button');require(all('[data-curve-point]').length===2,'Curve gesture did not undo in one operation');
    click('#redo-button');require(all('[data-curve-point]').length===3,'Curve gesture redo failed');
    choosePoint('curve',1);set('[data-curve-coordinate="0"]',.4);set('[data-curve-coordinate="1"]',.8);
    require(Number($('[data-curve-coordinate="1"]').value)===.8,'Numeric curve editing did not persist');
    set('[data-graph-add-type]','mask');click('[data-graph-action="add"]');
    result.mask_id=$('[data-graph-output]').value;
    set('[data-node-param="shape"]','polygon');
    dragPoint('polygon',0,[.1,.85],[.24,.7]);
    require(Math.abs(Number($('[data-polygon-coordinate="0"]').value)-.24)<.001,'Polygon handle did not move');
    click('#undo-button');require(Number($('[data-polygon-coordinate="0"]').value)===.1,'Polygon drag did not undo as one gesture');
    click('#redo-button');require(Math.abs(Number($('[data-polygon-coordinate="0"]').value)-.24)<.001,'Polygon drag redo failed');
    set('[data-polygon-coordinate="0"]',.2);set('[data-polygon-coordinate="1"]',.75);
    set('[data-node-param="rotation"][type="number"]',30);
    set('[data-node-param="width"][type="number"]',.9);set('[data-node-param="height"][type="number"]',.9);
    require($('[data-graph-status]').textContent==='3 nodes · 3 in output','Curve and mask are not connected to the source/output chain');
    mark('svg_curve_and_polygon_gestures_connected_graph');

    await until(()=>$('svg.clip-waveform path')?.getAttribute('d')?.length>100,'Decoded source waveform did not reach the timeline',2000);
    result.waveform_path=$('svg.clip-waveform path').getAttribute('d');
    require($('svg.clip-waveform').getAttribute('aria-label')==='Decoded source audio waveform','Waveform is not marked as decoded audio');
    mark('actual_decoded_waveform');
    click('[data-mode="color"]');field('grade.exposure',.25);
    result.paused_frame=await exactFrame();
    result.scopes={};
    for(const mode of ['histogram','waveform','vectorscope']){
      set('#scope-mode',mode);const evidence=canvasEvidence($('#scope-canvas'));
      require(!$('#color-scopes').hidden&&evidence.ink_pixels>50&&evidence.unique_colors>3,'Scope did not measure rendered pixels: '+mode);
      result.scopes[mode]=evidence;
    }
    require(new Set(Object.values(result.scopes).map(item=>item.hash)).size===3,'Scope modes produced the same raster');
    set('#scope-mode','histogram');mark('exact_paused_png_and_three_rendered_scopes');
    click('#save-project');
    await until(()=>$('#save-state').textContent==='SAVED LOCALLY'&&!$('#project-select').disabled&&!$('#save-project').disabled,'Project save left an operation blocker',1500);
    mark('save_shared_project');

    if(profile==='preview')click('#preview-render');else{click('#export-button');click('[data-export="h264"]');}
    await until(()=>['Render complete','Job failed','Job cancelled'].includes($('#job-label')?.textContent),'Real render did not complete within the bounded test',5000);
    require($('#job-label').textContent==='Render complete','The render failed');
    await until(()=>!$('#render-video').hidden&&$('#render-video').readyState>=2&&!$('#download-job').hidden,'Actual exported video did not load',1700);
    click('#play-button');await until(()=>$('#render-video').currentTime>.08,'WKWebView did not play the actual output',1400);
    result.video_src=$('#render-video').getAttribute('src');result.video_current_time=$('#render-video').currentTime;
    result.download_href=$('#download-job').getAttribute('href');
    if(!$('#render-video').paused)click('#play-button');
    require(!$('#project-select').disabled&&!$('#save-project').disabled,'Finished render left editing blocked');
    mark('real_'+profile+'_render_and_native_playback');
    click('#source-preview');result.paused_frame=await exactFrame();
    require(!$('#color-scopes').hidden,'Returning to the editor hid the color scopes');
    mark('return_to_current_frame_after_render');
    return {...result,passed:true,steps,timings,elapsed_ms:Math.round(performance.now()-began)};
  }catch(error){
    return {...result,passed:false,steps,timings,error:String(error),timecode:$('#timecode')?.textContent||'',toast:$('#toast')?.textContent||'',frame_status:$('#frame-status')?.textContent||'',job_label:$('#job-label')?.textContent||'',job_detail:$('#job-detail')?.textContent||'',elapsed_ms:Math.round(performance.now()-began)};
  }
})();
