/* Interactive composition traversal; exact finishing frames use the export graph. */
(()=>{
  'use strict';
  const buffers=[];
  let decodedPictures=null;
  let transportClock=null,preparing=false,buffering=null;
  const nearest=value=>value<0?-Math.floor(-value+.5):Math.floor(value+.5);
  function clockTicks(project){
    const labels=[[23.976,24000],[29.97,30000],[59.94,60000]],label=labels.find(([fps])=>Math.abs(project.fps-fps)<.00001);
    const rate=project.frame_rate||(label?{numerator:label[1],denominator:1001}:{numerator:project.fps,denominator:1});
    return rate.denominator*Math.min(10000,Math.floor(2147483647/rate.numerator));
  }
  function sampleSequenceFrame(clip,frame,project,sourceLength){
    const local=Math.max(0,Math.min(clip.duration-1,Math.floor(frame-clip.start))),speed=clip.speed??1,sourceIn=clip.in??0;
    const output=clip.reverse?clip.duration-1-local:local;
    if(speed===1&&Number.isInteger(sourceIn))return Math.max(0,Math.min(sourceLength-1,sourceIn+output));
    // The child is already on the project clock. Match the export graph's
    // high-resolution PTS rounding followed by nearest output-frame rounding;
    // fractional in points close to half-frame ties require both stages.
    const ticks=clockTicks(project),limit=Math.min(sourceLength-1,Math.max(0,Math.ceil(sourceIn+clip.duration*speed)-1));
    let low=0,high=limit;
    while(low<high){const middle=Math.floor((low+high+1)/2),pts=nearest(nearest((middle-sourceIn)*ticks/speed)/ticks);if(pts<=output)low=middle;else high=middle-1;}
    return low;
  }
  function draw({project,frame,audioFrame=frame,transportEpoch=0,context,width,height,mediaFor,ensureAudio,playing,activeIds,revision}){
    const edit=window.CinematicumEditing,assets=new Map(project.assets.map(a=>[a.id,a]));
    if(!decodedPictures&&window.CinematicumDecodedFrameCache)decodedPictures=new window.CinematicumDecodedFrameCache();
    const pictureDecoders=new Set();
    const clocks=[],decoders=[],lockedVoices=new Set();let pending=false;
    if(!playing||buffering?.epoch!==transportEpoch)buffering=null;
    const sequences=new Map([[project.sequence_id||'main',project],...(project.sequences||[]).map(s=>[s.id,s])]);
    function surface(depth){
      const factor=Math.min(1,1920/Math.max(width,height)),w=Math.max(2,Math.round(width*factor)),h=Math.max(2,Math.round(height*factor));
      let canvas=buffers[depth];if(!canvas){canvas=document.createElement('canvas');buffers[depth]=canvas;}
      if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
      const ctx=canvas.getContext('2d');ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,w,h);
      return {canvas,ctx,w,h};
    }
    const sequenceLength=sequence=>Math.max(sequence.sequence_duration||0,...['clips','titles','captions'].flatMap(field=>(sequence[field]||[]).map(item=>item.start+item.duration)));
    const contains=(clip,at)=>at>=clip.start&&at<clip.start+clip.duration;
    const audioSourceFrame=(clip,at)=>{
      const local=Math.max(0,Math.min(clip.duration,at-clip.start)),speed=clip.speed??1;
      return (clip.in??0)+(clip.reverse?clip.duration-local:local)*speed;
    };
    function sourceMedia(clip,key,asset,sourceFrame,rate,backwards,sound,clipGain,clipLeft,clipRight,nested,precisePicture=false){
      const media=mediaFor(key===clip.id?clip:{...clip,id:key},asset),el=media.el;
      media.nested=nested;media.ownerClipId=clip.id;media.revision=revision;activeIds.add(key);
      if(media.kind!=='image'){
        const seek=sourceFrame/project.fps,tolerance=playing?(precisePicture?.75/project.fps:.16):.01;
        const source=media.requestUrl||media.url||el.currentSrc||el.src;
        const identity=media.kind==='video'&&source?JSON.stringify([project.id,asset.id,asset.sha256||null,source]):null;
        const cacheIntent=identity&&(!playing||backwards);
        media.decodedPicture=cacheIntent?decodedPictures?.get(identity,seek):null;
        // Native forward decoding already owns a playback queue. Copying every
        // displayed 4K frame into RGBA snapshots would compete with that queue.
        // Retain snapshots only for explicit pause/scrub/reverse reuse.
        if(cacheIntent&&decodedPictures){pictureDecoders.add(el);decodedPictures.observe(el,identity,()=>!media.disposed);}
        const playbackRate=media.kind==='audio'?rate:Math.max(.0625,Math.min(16,rate));
        // Native media setters may rebuild an AVFoundation audio tap even if
        // the requested value is unchanged. Keep steady playback untouched.
        if(el.playbackRate!==playbackRate){try{el.playbackRate=playbackRate;}catch(error){}}
        if('preservesPitch'in el&&!el.preservesPitch)el.preservesPitch=true;
        // Audio decoders have a startup/output delay. Repeatedly seeking them
        // toward a wall clock flushes their native audio tap and creates a loop
        // of gaps. Seek once per transport/source edit, then let the audio clock
        // drive transport. Picture-only decoders can continue to resynchronize.
        const syncKey=JSON.stringify([transportEpoch,rate,backwards,Math.round((seek-audioFrame/project.fps*(backwards?-rate:rate))*1e6)]);
        const mustSeek=!media.decodedPicture&&(!sound||!playing||media.audioSyncKey!==syncKey);
        if(mustSeek&&Number.isFinite(el.duration)&&el.readyState>=1){
          if(Math.abs(el.currentTime-seek)>(sound?.005:tolerance)){try{el.currentTime=Math.min(seek,Math.max(0,el.duration-.001));}catch(error){}}
          if(sound&&playing)media.audioSyncKey=syncKey;
        }
        if(!playing)media.audioSyncKey=null;
        if(identity&&decodedPictures&&(!playing||backwards)&&!media.decodedPicture&&!el.seeking&&el.readyState>=2){
          decodedPictures.capture(identity,el.currentTime,el);
          media.decodedPicture=decodedPictures.get(identity,seek);
        }
        const routing=sound?ensureAudio(media,clip,asset,{playbackRate:rate,sourceTime:seek,reverse:backwards}):null,audible=sound&&routing?.ready!==false;
        const muted=media.source?false:!audible;
        if(el.muted!==muted)el.muted=muted;
        if(media.stereo)media.stereo.gain.value=(media.audioRoute?.channels??asset.audio_channels)===1?Math.SQRT1_2:1;
        if(media.gain){if(el.volume!==1)el.volume=1;media.gain.gain.value=!audible?0:clipGain;media.left.gain.value=clipLeft;media.right.gain.value=clipRight;}
        else{const volume=Math.max(0,Math.min(1,!audible?0:clipGain));if(el.volume!==volume)el.volume=volume;}
        if(sound){
          const waiting=routing?.state==='pending'||(audible&&!el.error&&(el.readyState<2||el.seeking));
          if(waiting)pending=true;
          // A fade beginning at zero still needs the same clock from its first
          // sample. Track mute/solo already exclude inactive sound.
          if(playing&&audible)clocks.push({key,el,frame:audioFrame,sourceTime:seek,rate:backwards?-rate:rate,fps:project.fps});
        }
        const canPlay=sound?audible:!backwards;decoders.push({media,sound,canPlay});
        if(playing&&canPlay&&!buffering){if(el.paused&&!el.ended)el.play().catch(()=>{});}else if(!el.paused)el.pause();
      }
      return media;
    }
    function visit(sequence,at,audioAt,target,W,H,prefix,depth,speed,gain,left,right,reversed,withPicture=true,withAudio=true){
      if(depth>8)return;
      const scope={...project,...sequence},clips=(sequence.clips||[]).filter(c=>edit.active(scope,c.track)&&((withPicture&&contains(c,at))||(withAudio&&contains(c,audioAt)))).sort((a,b)=>a.track-b.track);
      for(const clip of clips){
        const pictureActive=withPicture&&contains(clip,at)&&clip.track>=0,audioActive=withAudio&&!clip.retime&&contains(clip,audioAt);
        const local=at-clip.start,audioLocal=audioAt-clip.start,pose=edit.pose(clip,local),pan=clip.audio?.pan||0;
        const clipGain=audioActive?gain*edit.audioGain(scope,clip,audioLocal):0,clipLeft=left*Math.min(1,1-pan),clipRight=right*Math.min(1,1+pan);
        const rate=speed*(clip.speed??1),backwards=reversed!==Boolean(clip.reverse),soundFrame=audioSourceFrame(clip,audioAt);
        const key=prefix?prefix+'/'+clip.id:clip.id;
        let picture=null,aw=project.width,ah=project.height,asset=null;
        if(clip.sequence_id){
          const child=sequences.get(clip.sequence_id);if(!child)continue;
          const sourceFrame=pictureActive?sampleSequenceFrame(clip,at,project,sequenceLength(child)):0;
          const layer=surface(depth);
          visit(child,sourceFrame,soundFrame,layer.ctx,layer.w,layer.h,key,depth+1,rate,clipGain,clipLeft,clipRight,backwards,pictureActive,audioActive);
          picture=layer.canvas;
        }else{
          asset=assets.get(clip.asset_id);if(!asset||asset.kind==='scene')continue;
          // A nested picture samples an integer child frame. Its sound keeps a
          // continuous source clock, including when a picture cut is sampled
          // one frame before/after the audio cut by a fast or fractional retime.
          // Separate original-source audio elements also keep picture proxies
          // from changing the source's stream identities and channel layout.
          const separateSound=asset.kind==='video';
          if(pictureActive&&asset.kind!=='audio'){
            const media=sourceMedia(clip,key,asset,edit.sourceFrame(clip,at),rate,backwards,!separateSound&&audioActive,clipGain,clipLeft,clipRight,Boolean(prefix),Boolean(prefix)),el=media.el;
            if(media.decodedPicture||(media.kind==='image'?el.complete&&el.naturalWidth:el.readyState>=2)){picture=media.decodedPicture||el;aw=asset.width||el.videoWidth||el.naturalWidth;ah=asset.height||el.videoHeight||el.naturalHeight;}
          }
          const resolved=window.CinematicumMulticam?.resolveAudio(project,clip,asset)||{clip,asset};
          const soundClip=resolved.clip,soundAsset=resolved.asset;
          if(audioActive&&soundAsset?.has_audio&&(separateSound||asset.kind==='audio'||!pictureActive)){
            const origin=resolved.clockOrigin;
            let audioKey=resolved.group?(prefix?prefix+'/':'')+'multicam-sound/'+resolved.group.id+'/'+clip.track+'/'+origin+'/'+rate+'/'+backwards:(asset.kind==='video'?key+'/sound':key);
            // Distinct overlapping instances still mix independently. Consecutive
            // picture cuts reuse the continuous locked-source PCM voice.
            if(resolved.group){if(lockedVoices.has(audioKey))audioKey+='/'+clip.id;lockedVoices.add(audioKey);}
            sourceMedia(soundClip,audioKey,{...soundAsset,kind:'audio'},audioSourceFrame(soundClip,audioAt),rate,backwards,true,clipGain,clipLeft,clipRight,Boolean(prefix));
          }
        }
        if(!pictureActive||!picture||!aw||!ah)continue;
        const motion=asset?edit.trackingOffset(clip,local,scope,asset,pose):{x:0,y:0},fit=Math.min(W/aw,H/ah)*pose.scale,g=clip.grade||{},effects=clip.effects||{};
        target.save();
        const dissolve=sequence.otio_dissolve,weight=dissolve?Math.max(0,Math.min(1,Math.floor(at)/(dissolve.in_offset+dissolve.out_offset))):1;
        target.globalAlpha=Math.max(0,Math.min(1,pose.opacity*(dissolve?(clip.track===0?1-weight:weight):1)));
        // Canvas 'lighter' adds associated color and alpha. The two operands
        // of an OTIO dissolve sum to one coverage weight on a clear surface.
        if(dissolve)target.globalCompositeOperation='lighter';
        target.translate(W/2+(pose.x+motion.x)*W,H/2+(pose.y+motion.y)*H);target.rotate(pose.rotation*Math.PI/180);
        target.filter=`brightness(${2**(g.exposure||0)}) contrast(${g.contrast??1}) saturate(${g.saturation??1}) blur(${(effects.blur||0)*W/project.width}px)`;
        try{target.drawImage(picture,-aw*fit/2,-ah*fit/2,aw*fit,ah*fit);}catch(error){}
        target.restore();
      }
      if(!withPicture)return;
      for(const title of sequence.titles||[]){
        const local=at-title.start;if(local<0||local>=title.duration)continue;
        const fade=title.fade||0,alpha=fade?Math.min(1,local/fade,(title.duration-local)/fade):1,scale=W/project.width;
        target.save();target.globalAlpha=Math.max(0,Math.min(1,alpha));target.fillStyle=title.color||'#fff';target.font=`${(title.size||48)*scale}px sans-serif`;target.textAlign='center';target.textBaseline='middle';
        const lines=(title.text||'').split('\n'),lineHeight=(title.size||48)*1.2*scale;
        lines.forEach((line,i)=>target.fillText(line,W*(.5+(title.x||0)),H*(.5+(title.y||0))+(i-(lines.length-1)/2)*lineHeight));target.restore();
      }
    }
    visit(project,frame,audioFrame,context,width,height,'',0,1,1,1,1,false);
    decodedPictures?.retain(pictureDecoders);
    preparing=pending;
    if(playing&&pending){
      // A new overlapping source must start at its authored position. Hold all
      // active decoders together while it prepares, rather than allowing a
      // ready master to run past the missing source's beginning.
      buffering??={epoch:transportEpoch,key:transportClock?.key,aligned:new Set()};
      for(const {media,sound}of decoders){
        if(!media.el.paused)media.el.pause();
        if(sound&&!buffering.aligned.has(media)){media.audioSyncKey=null;buffering.aligned.add(media);}
      }
      transportClock={waiting:true,frame:audioFrame,key:buffering.key};return;
    }
    if(buffering){
      buffering=null;
      for(const {media,canPlay}of decoders)if(canPlay&&media.el.paused&&!media.el.ended)media.el.play().catch(()=>{});
    }
    const previous=transportClock?.key;
    transportClock=clocks.find(candidate=>candidate.key===previous)||clocks[0]||null;
  }
  function clock(){
    const value=transportClock;if(!value)return null;
    if(value.waiting)return {waiting:true,frame:value.frame};
    const {el}=value;if(el.error)return null;
    if(el.seeking||(el.paused&&!el.ended))return {waiting:true,frame:value.frame,source:value.key};
    const frame=value.frame+(el.currentTime-value.sourceTime)*value.fps/value.rate;
    // Browser end times can land just below the final sample boundary. Permit
    // transport to leave a completed source and continue into a cut or gap.
    return {waiting:false,frame:el.ended?Math.ceil(frame-1e-7):frame,source:value.key};
  }
  window.CinematicumSequencePlayback={draw,sampleSequenceFrame,clock,ready:()=>!preparing,cacheStats:()=>decodedPictures?.stats()||null,clear(){transportClock=null;preparing=false;buffering=null;decodedPictures?.clear();for(const canvas of buffers){canvas.width=1;canvas.height=1;}buffers.length=0;}};
})();
