// Play the real, byte-identical admitted generation through shipped controls.
// This script only observes DOM/canvas state and clicks existing controls. It
// neither injects application state nor creates an export or substitute video.
return await (async()=>{
  const began=performance.now(),deadline=began+11000,steps=[],samples=[];
  const result={scope:'Actual generated source playback in an isolated ENGINE TEST project',samples};
  const $=selector=>document.querySelector(selector),sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const detail=()=>'; toast='+($('#toast')?.textContent||'')+'; frame='+($('#frame-status')?.textContent||'')+'; transport='+($('#play-button')?.getAttribute('aria-label')||'');
  function require(value,label){if(!value)throw Error(label+detail());}
  function click(selector){const element=$(selector);require(element&&!element.disabled&&!element.hidden,'Unavailable control '+selector);element.scrollIntoView({block:'nearest',inline:'nearest'});element.click();}
  async function until(predicate,label,maximum=2200){const end=Math.min(deadline,performance.now()+maximum);while(performance.now()<end){if(predicate())return;await sleep(25);}throw Error(label+detail());}
  function readPicture(){
    const canvas=$('#preview-canvas'),ctx=canvas.getContext('2d'),pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data,grid=[];
    let hash=2166136261;
    for(let row=0;row<8;row++)for(let column=0;column<12;column++){
      const x=Math.min(canvas.width-1,Math.floor((column+.5)*canvas.width/12)),y=Math.min(canvas.height-1,Math.floor((row+.5)*canvas.height/8)),offset=(y*canvas.width+x)*4;
      for(let channel=0;channel<3;channel++){const value=pixels[offset+channel];grid.push(value);hash=Math.imul(hash^value,16777619)>>>0;}
    }
    const luma=[];for(let i=0;i<grid.length;i+=3)luma.push((54*grid[i]+183*grid[i+1]+19*grid[i+2])/256);
    return {grid,hash:hash.toString(16),mean:luma.reduce((a,b)=>a+b,0)/luma.length,range:Math.max(...luma)-Math.min(...luma)};
  }
  function originalPictureIsVisible(){
    require($('#source-preview').classList.contains('active'),'The editor picture is not selected');
    require(!$('#preview-canvas').hidden&&getComputedStyle($('#preview-canvas')).display!=='none','The source canvas is hidden');
    require($('#render-video').hidden&&!$('#render-video').getAttribute('src'),'Playback used an exported video');
    require($('#processed-frame').hidden,'A paused rendered frame is covering live source playback');
  }
  try{
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST')&&$('.media-item[data-asset]'),'Actual take did not bootstrap into the media bin',4000);
    require(document.querySelectorAll('.media-item[data-asset]').length===1,'The isolated scope contains more than the actual take');
    require(!$('.timeline-clip'),'The isolated timeline was prepopulated');
    result.project_id=$('#project-select').value;result.asset_id=$('.media-item[data-asset]').dataset.asset;
    require($('.media-name').textContent.includes('actual generated take'),'The test media is not labelled as the actual generated take');
    click('[data-add="'+result.asset_id+'"]');
    await until(()=>document.querySelectorAll('.timeline-clip[data-type="clip"]').length===1,'Add did not create a real timeline clip');
    result.clip_id=$('.timeline-clip[data-type="clip"]').dataset.clip;steps.push('actual_media_added_by_shipped_add_control');
    click('#jump-start');
    await until(()=>{const p=readPicture();return p.mean>1&&p.mean<254&&p.range>3;},'Source decoder produced no picture',2500);
    result.width=$('#preview-canvas').width;result.height=$('#preview-canvas').height;result.start_timecode=$('#timecode').textContent;
    click('#play-button');await until(()=>$('#play-button').getAttribute('aria-label')==='Pause timeline','Actual source transport did not start',3000);
    const playbackBegan=performance.now();
    while(performance.now()<deadline&&performance.now()-playbackBegan<2500){
      if($('#play-button').getAttribute('aria-label')!=='Pause timeline')break;
      originalPictureIsVisible();const picture=readPicture();
      if(picture.mean>1&&picture.range>3&&samples.at(-1)?.hash!==picture.hash&&samples.length<32){
        samples.push({timecode:$('#timecode').textContent,elapsed_ms:Math.round(performance.now()-playbackBegan),...picture});
      }
      await sleep(15);
    }
    if($('#play-button').getAttribute('aria-label')==='Pause timeline')click('#play-button');
    result.end_timecode=$('#timecode').textContent;result.render_video_src=$('#render-video').getAttribute('src');
    require(new Set(samples.map(item=>item.hash)).size>=3,'Live playback did not show at least three distinct source images');
    require(result.end_timecode!==result.start_timecode&&samples.some(item=>item.timecode!==result.start_timecode),'Timeline did not advance during source playback');
    steps.push('source_canvas_played_changing_actual_movie_without_render_substitute');
    click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','The timeline edit was not saved',2200);
    steps.push('actual_timeline_save_completed');
    result.source_requests=performance.getEntriesByType('resource').filter(entry=>entry.name.includes('/media/'+result.asset_id)).map(entry=>({url:new URL(entry.name).pathname,initiator:entry.initiatorType}));
    return {...result,passed:true,steps,elapsed_ms:Math.round(performance.now()-began)};
  }catch(error){return {...result,passed:false,steps,error:String(error),elapsed_ms:Math.round(performance.now()-began)};}
})();
