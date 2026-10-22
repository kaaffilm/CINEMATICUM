/* Bounded decoded picture snapshots. These are display derivatives, not masters. */
(()=>{
  'use strict';
  class DecodedFrameCache {
    constructor({maxBytes=96*1024*1024,maxEntries=120,createSurface=()=>document.createElement('canvas')}={}){
      if(!Number.isSafeInteger(maxBytes)||maxBytes<0||!Number.isSafeInteger(maxEntries)||maxEntries<0)throw new TypeError('Invalid decoded-frame cache budget');
      this.maxBytes=maxBytes;this.maxEntries=maxEntries;this.createSurface=createSurface;
      this.entries=new Map();this.observers=new Map();this.bytes=0;this.hits=0;this.misses=0;
    }
    key(identity,time){
      // Quantize seconds, never project/source frame indices: mixed frame rates
      // and VFR pictures must not borrow a nearby decoded sample.
      return typeof identity==='string'&&identity&&Number.isFinite(time)&&time>=0?JSON.stringify([identity,time.toFixed(6)]):null;
    }
    get(identity,time){
      const key=this.key(identity,time),entry=key&&this.entries.get(key);
      if(!entry){this.misses++;return null;}
      this.entries.delete(key);this.entries.set(key,entry);this.hits++;return entry.surface;
    }
    drop(key){
      const entry=this.entries.get(key);if(!entry)return;
      this.entries.delete(key);this.bytes-=entry.bytes;
      // Resetting a canvas relinquishes its backing store, including any GPU
      // allocation the browser chose. There is no asynchronous bitmap owner.
      entry.surface.width=1;entry.surface.height=1;
    }
    capture(identity,time,video){
      const key=this.key(identity,time),width=video.videoWidth,height=video.videoHeight,bytes=width*height*4;
      if(!key||video.seeking||video.readyState<2||!Number.isSafeInteger(width)||!Number.isSafeInteger(height)||width<1||height<1||!Number.isSafeInteger(bytes)||bytes>this.maxBytes||!this.maxEntries)return null;
      if(this.entries.has(key)){const entry=this.entries.get(key);this.entries.delete(key);this.entries.set(key,entry);return entry.surface;}
      while(this.entries.size&&(this.bytes+bytes>this.maxBytes||this.entries.size>=this.maxEntries))this.drop(this.entries.keys().next().value);
      let surface;
      try{
        surface=this.createSurface();surface.width=width;surface.height=height;
        const context=surface.getContext('2d');if(!context)throw new Error('No decoded-frame canvas context');
        // Copy synchronously while this decoded sample is current. A later
        // seek/callback cannot replace pixels underneath a cached picture.
        context.drawImage(video,0,0,width,height);
      }catch(error){if(surface){surface.width=1;surface.height=1;}return null;}
      this.entries.set(key,{surface,bytes});this.bytes+=bytes;return surface;
    }
    observe(video,identity,isCurrent=()=>true){
      if(typeof video.requestVideoFrameCallback!=='function')return;
      const previous=this.observers.get(video);
      if(previous?.identity===identity)return;
      if(previous)this.unobserve(video);
      const record={identity,id:null,source:video.currentSrc||video.src};this.observers.set(video,record);
      const next=()=>{
        if(this.observers.get(video)!==record)return;
        try{record.id=video.requestVideoFrameCallback((now,metadata)=>{
          if(this.observers.get(video)!==record)return;
          record.id=null;
          if(!isCurrent()||(video.currentSrc||video.src)!==record.source){this.unobserve(video);return;}
          this.capture(identity,metadata.mediaTime,video);next();
        });}catch(error){this.unobserve(video);}
      };
      next();
    }
    unobserve(video){
      const record=this.observers.get(video);if(!record)return;
      this.observers.delete(video);
      if(record.id!==null&&typeof video.cancelVideoFrameCallback==='function')try{video.cancelVideoFrameCallback(record.id);}catch(error){}
    }
    retain(active){for(const video of this.observers.keys())if(!active.has(video))this.unobserve(video);}
    clear(){for(const video of this.observers.keys())this.unobserve(video);for(const key of this.entries.keys())this.drop(key);}
    stats(){return {entries:this.entries.size,bytes:this.bytes,maxBytes:this.maxBytes,maxEntries:this.maxEntries,observers:this.observers.size,hits:this.hits,misses:this.misses};}
  }
  window.CinematicumDecodedFrameCache=DecodedFrameCache;
})();
