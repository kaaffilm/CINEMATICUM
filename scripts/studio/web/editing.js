/* Shared timeline evaluation. The equations match engine.py's export graph. */
(() => {
  'use strict';
  const clamp=(n,a,b)=>Math.min(b,Math.max(a,n));
  const properties=['x','y','scale','opacity','rotation','volume'];
  const defaults={x:0,y:0,scale:1,opacity:1,rotation:0,volume:1};
  const easings={linear:u=>u,constant:()=>0,ease_in:u=>u*u,
    ease_out:u=>1-(1-u)*(1-u),ease_in_out:u=>u*u*(3-2*u)};
  function curve(clip,key,frame) {
    frame+=clip.animation_offset??0;
    const points=[{frame:0,value:clip[key]??defaults[key],interpolation:'linear'}];
    for(const k of [...(clip.keyframes||[])].sort((a,b)=>a.frame-b.frame)) {
      if(k[key]===undefined)continue;
      const point={frame:k.frame,value:k[key],interpolation:k.interpolation||'linear'};
      if(k.frame===0)points[0]=point;else points.push(point);
    }
    points.sort((a,b)=>a.frame-b.frame);
    if(frame<=points[0].frame)return points[0].value;
    for(let i=1;i<points.length;i++) {
      const a=points[i-1],b=points[i];
      if(frame<b.frame){const u=clamp((frame-a.frame)/(b.frame-a.frame),0,1);return a.value+(b.value-a.value)*(easings[a.interpolation]||easings.linear)(u);}
    }
    return points.at(-1).value;
  }
  function pose(clip,frame){return Object.fromEntries(properties.map(key=>[key,curve(clip,key,frame)]));}
  function measuredValue(keys,key,frame) {
    if(!keys?.length)return 0;
    if(frame<=keys[0].frame)return keys[0][key];
    for(let i=1;i<keys.length;i++){const a=keys[i-1],b=keys[i];if(frame<b.frame){const u=(frame-a.frame)/(b.frame-a.frame);return a[key]+(b[key]-a[key])*u;}}
    return keys.at(-1)[key];
  }
  function trackingOffset(clip,frame,project,asset,value=pose(clip,frame)) {
    if(!clip.tracking?.keys?.length)return {x:0,y:0};
    const at=frame+(clip.animation_offset??0),fit=Math.min(project.width/asset.width,project.height/asset.height);
    const width=Math.max(2,Math.trunc(asset.width*fit*value.scale/2)*2),height=Math.max(2,Math.trunc(asset.height*fit*value.scale/2)*2);
    const dx=measuredValue(clip.tracking.keys,'x',at)*width,dy=measuredValue(clip.tracking.keys,'y',at)*height,angle=value.rotation*Math.PI/180;
    return {x:(dx*Math.cos(angle)-dy*Math.sin(angle))/project.width,y:(dx*Math.sin(angle)+dy*Math.cos(angle))/project.height};
  }
  function ensureAnimationDomain(clip) {
    const offset=clip.animation_offset??0;
    clip.animation_start=Math.min(clip.animation_start??0,offset);
    clip.animation_duration=Math.max(clip.animation_duration??clip.duration,offset+clip.duration);
    return clip;
  }
  function preserveAnimation(clip,original,offset=0) {
    clip.animation_start=original.animation_start??0;
    clip.animation_duration=original.animation_duration??original.duration;
    clip.animation_offset=(original.animation_offset??0)+offset;
    clip.keyframes=JSON.parse(JSON.stringify(original.keyframes||[]));
    // Extending the editable domain does not create keys or move curves.
    // Audio fades retain their own original domain so their endpoint stays put.
    ensureAnimationDomain(clip);
    if(clip.audio){clip.audio.fade_duration=original.audio?.fade_duration??original.duration;clip.audio.fade_offset=(original.audio?.fade_offset??0)+offset;}
    return clip;
  }
  function retimeExtraChannels(clip,ratio) {
    const rescale=keys=>[...new Map(keys.map(k=>{const next={...k,frame:Math.round(k.frame*ratio)};return [next.frame,next];})).values()].sort((a,b)=>a.frame-b.frame);
    const frames=[];
    if(clip.tracking){clip.tracking.keys=rescale(clip.tracking.keys);frames.push(...clip.tracking.keys.map(k=>k.frame));}
    for(const node of clip.compositor?.nodes||[])for(const name of Object.keys(node.animation||{})){node.animation[name]=rescale(node.animation[name]);frames.push(...node.animation[name].map(k=>k.frame));}
    if(frames.length){clip.animation_start=Math.min(clip.animation_start??0,...frames);clip.animation_duration=Math.max(clip.animation_duration??clip.duration,...frames.map(f=>f+1));}
  }
  function track(project,id) {
    return {id,name:id<0?'Audio '+Math.abs(id):'Video '+(id+1),mute:false,solo:false,locked:false,gain:1,...(project.tracks||[]).find(t=>t.id===id)};
  }
  function tracks(project) {
    const ids=new Set([...(project.tracks||[]).map(t=>t.id),...(project.clips||[]).map(c=>c.track)]);
    if(!ids.size){ids.add(0);ids.add(1);ids.add(-1);ids.add(-2);}
    return [...ids].sort((a,b)=>b-a).map(id=>track(project,id));
  }
  function active(project,id) {
    const t=track(project,id),solo=tracks(project).some(x=>(x.id<0)===(id<0)&&x.solo);
    return Boolean(!t.mute&&(!solo||t.solo));
  }
  function sourceFrame(clip,frame) {
    const local=clamp(frame-clip.start,0,clip.duration-1),speed=clip.speed??1;
    return clip.in+(clip.reverse?(clip.duration-1-local)*speed:local*speed);
  }
  function audioGain(project,clip,local) {
    if(!active(project,clip.track)||clip.reverse)return 0;
    const a=clip.audio||{},fadeIn=a.fade_in||0,fadeOut=a.fade_out||0,at=local+(a.fade_offset??0),end=a.fade_duration??clip.duration;
    const fade=Math.min(1,fadeIn?Math.max(0,at)/fadeIn:1,fadeOut?Math.max(0,end-at)/fadeOut:1);
    return curve(clip,'volume',local)*(track(project,clip.track).gain??1)*fade;
  }
  function trim(clip,edge,requested,max=Infinity,still=false) {
    const speed=clip.speed??1,sourceIn=clip.in??0;
    if(edge==='left') {
      const available=still?Infinity:clip.reverse?(max-sourceIn-clip.duration*speed)/speed:sourceIn/speed;
      const shift=clamp(Math.round(requested-clip.start),Math.ceil(Math.max(-clip.start,-available)),clip.duration-1);
      return {start:clip.start+shift,duration:clip.duration-shift,in:still?0:sourceIn+(clip.reverse?0:shift*speed),offset:shift};
    }
    const available=still?Infinity:clip.reverse?clip.duration+sourceIn/speed:(max-sourceIn)/speed;
    const duration=clamp(Math.round(requested-clip.start),1,Math.max(1,Math.floor(available+1e-8)));
    return {start:clip.start,duration,in:still?0:sourceIn+(clip.reverse?(clip.duration-duration)*speed:0),offset:0};
  }
  function envelopePath(wave,clip,project,channel=0) {
    const peaks=wave?.peaks?.[channel];if(!peaks?.max?.length)return '';
    const samples=128,upper=[],lower=[],bins=wave.bins,sourceFrames=wave.duration*project.fps;
    for(let i=0;i<samples;i++) {
      const f=sourceFrame(clip,clip.start+i/(samples-1)*Math.max(0,clip.duration-1));
      const n=clamp(Math.floor(f/sourceFrames*bins),0,bins-1),x=i/(samples-1)*100;
      upper.push(`${x.toFixed(2)},${(50-(peaks.max[n]||0)*44).toFixed(2)}`);
      lower.push(`${x.toFixed(2)},${(50-(peaks.min[n]||0)*44).toFixed(2)}`);
    }
    return 'M'+upper.join(' L')+' L'+lower.reverse().join(' L')+' Z';
  }
  window.CinematicumEditing={clamp,properties,defaults,easings,curve,pose,measuredValue,trackingOffset,ensureAnimationDomain,preserveAnimation,retimeExtraChannels,track,tracks,active,sourceFrame,audioGain,trim,envelopePath};
})();
