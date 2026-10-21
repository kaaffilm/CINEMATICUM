/* Exact frame feedback and scopes for CINEMATICUM's shared timeline. */
(() => {
  'use strict';
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  class FrameViewer {
    constructor({request,getState,prepareSnapshot,image,status,scopes,scopeMode}) {
      Object.assign(this,{request,getState,prepareSnapshot,image,status,scopes,scopeMode});
      this.serial=0;this.job=null;this.timer=null;this.identity='';this.lastImage=null;
      this.scopeMode?.addEventListener('change',()=>this.drawScopes());
    }
    needsFrame(state) {
      return state.project&&!state.playing&&!state.rendered&&state.mode!=='3d'&&state.mode!=='generate'&&
        (state.mode==='color'||state.mode==='composite'||state.project.clips.some(c=>c.sequence_id||c.compositor||c.reverse||c.tracking||c.color_pipeline?.enabled));
    }
    invalidate() {
      clearTimeout(this.timer);const serial=++this.serial;
      this.clear();
      const s=this.getState();
      if(!this.needsFrame(s)||!s.project.clips.length&&!s.project.titles.length){this.status.hidden=true;return;}
      this.status.hidden=false;this.status.textContent='Rendering current frame…';this.status.classList.remove('error');
      this.timer=setTimeout(()=>this.render(serial),250);
    }
    async render(serial) {
      const s=this.getState(),projectId=s.project?.id,frame=Math.round(s.frame),revision=s.revision;
      if(serial!==this.serial||!this.needsFrame(s))return;
      if(this.job){this.request('/api/jobs/'+this.job+'/cancel',{method:'POST',body:{}}).catch(()=>{});this.job=null;}
      try {
        const project=await this.prepareSnapshot();
        if(serial!==this.serial||this.getState().project.id!==projectId)return;
        const job=await this.request(`/api/projects/${projectId}/frame-preview`,{method:'POST',body:{project,frame}});
        if(serial!==this.serial){this.request('/api/jobs/'+job.id+'/cancel',{method:'POST',body:{}}).catch(()=>{});return;}
        this.job=job.id;
        for(let attempts=0;attempts<240;attempts++) {
          if(serial!==this.serial)return;
          const result=await this.request('/api/jobs/'+job.id);
          if(result.state==='completed') {
            const now=this.getState();
            if(now.project.id!==projectId||now.frame!==frame||now.revision!==revision||now.playing||now.rendered)return;
            const picture=new Image();picture.src=result.result.url;
            await picture.decode();
            if(serial!==this.serial)return;
            this.lastImage=picture;this.image.src=picture.src;this.image.hidden=false;
            this.identity=`${projectId}:${revision}:${frame}`;
            this.status.textContent=`Rendered frame ${frame} · export graph`;this.job=null;
            this.drawScopes();return;
          }
          if(['failed','cancelled','interrupted'].includes(result.state))throw Error(result.error||'Frame preview stopped');
          await delay(160);
        }
        throw Error('Frame preview is still queued. Render the timeline to review the current output.');
      } catch(error) {
        if(serial!==this.serial)return;
        this.job=null;this.image.hidden=true;this.status.classList.add('error');
        this.status.textContent='Frame preview: '+error.message;
      }
    }
    clear() {
      this.identity='';this.image.hidden=true;this.lastImage=null;
      if(this.scopes){const context=this.scopes.getContext('2d');context.fillStyle='#0d1117';context.fillRect(0,0,this.scopes.width,this.scopes.height);}
      if(this.job){const old=this.job;this.job=null;this.request('/api/jobs/'+old+'/cancel',{method:'POST',body:{}}).catch(()=>{});}
    }
    hide() {clearTimeout(this.timer);this.serial++;this.clear();this.status.hidden=true;}
    drawScopes() {
      if(!this.lastImage||!this.scopes)return;
      const sample=document.createElement('canvas');sample.width=320;sample.height=180;
      const sc=sample.getContext('2d',{willReadFrequently:true});sc.drawImage(this.lastImage,0,0,320,180);
      const pixels=sc.getImageData(0,0,320,180).data;
      const c=this.scopes,ctx=c.getContext('2d'),w=c.width,h=c.height,mode=this.scopeMode?.value||'histogram';
      ctx.fillStyle='#0d1117';ctx.fillRect(0,0,w,h);ctx.strokeStyle='#29333e';ctx.lineWidth=1;
      for(let n=0;n<=4;n++){ctx.beginPath();ctx.moveTo(0,10+n*(h-20)/4);ctx.lineTo(w,10+n*(h-20)/4);ctx.stroke();}
      if(mode==='histogram') {
        const bins=[new Uint32Array(256),new Uint32Array(256),new Uint32Array(256)];
        for(let i=0;i<pixels.length;i+=4)for(let k=0;k<3;k++)bins[k][pixels[i+k]]++;
        const maximum=Math.max(1,...bins.flatMap(channel=>[...channel]));
        ['#ff756f','#7bdba4','#7cafff'].forEach((color,k)=>{
          ctx.strokeStyle=color;ctx.globalAlpha=.85;ctx.beginPath();
          for(let x=0;x<256;x++){const px=x/255*w,py=h-10-Math.log1p(bins[k][x])/Math.log1p(maximum)*(h-20);if(x)ctx.lineTo(px,py);else ctx.moveTo(px,py);}
          ctx.stroke();
        });
      } else if(mode==='waveform') {
        ctx.fillStyle='#9ae3be';ctx.globalAlpha=.065;
        for(let i=0;i<pixels.length;i+=4){const x=(i/4%320)/320*w,y=(.2126*pixels[i]+.7152*pixels[i+1]+.0722*pixels[i+2])/255;ctx.fillRect(x,10+(1-y)*(h-20),1.5,1.5);}
      } else {
        const r=Math.min(w,h)/2-12,cx=w/2,cy=h/2;
        ctx.strokeStyle='#485566';ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);ctx.moveTo(cx-r,cy);ctx.lineTo(cx+r,cy);ctx.moveTo(cx,cy-r);ctx.lineTo(cx,cy+r);ctx.stroke();
        ctx.fillStyle='#c2dcaf';ctx.globalAlpha=.065;
        for(let i=0;i<pixels.length;i+=12){const R=pixels[i]/255,G=pixels[i+1]/255,B=pixels[i+2]/255,Y=.2126*R+.7152*G+.0722*B;ctx.fillRect(cx+(B-Y)/1.8556*r*2,cy-(R-Y)/1.5748*r*2,1.5,1.5);}
      }
      ctx.globalAlpha=1;
    }
  }
  window.CinematicumFrameViewer=FrameViewer;
})();
