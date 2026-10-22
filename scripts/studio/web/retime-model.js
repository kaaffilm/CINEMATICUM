/* Shared output-frame clock for bounded, positive linear speed ramps. */
(() => {
  'use strict';
  const copy=value=>JSON.parse(JSON.stringify(value));
  const finite=(value,label)=>{if(typeof value!=='number'||!Number.isFinite(value))throw Error(label+' must be a finite number.');return value;};
  const integer=(value,label)=>{finite(value,label);if(!Number.isInteger(value))throw Error(label+' must be a whole number of output frames.');return value;};
  const gcd=(a,b)=>{a=a<0n?-a:a;while(b){const next=a%b;a=b;b=next;}return a;};
  function rational(n,d=1n){if(d===0n)throw Error('A rational source clock needs a positive denominator.');if(d<0n){n=-n;d=-d;}const divisor=gcd(n,d);return {n:n/divisor,d:d/divisor};}
  const add=(a,b)=>rational(a.n*b.d+b.n*a.d,a.d*b.d);
  const subtract=(a,b)=>rational(a.n*b.d-b.n*a.d,a.d*b.d);
  const multiply=(a,b)=>rational(a.n*b.n,a.d*b.d);
  const compare=(a,b)=>{const difference=a.n*b.d-b.n*a.d;return difference<0n?-1:difference>0n?1:0;};
  function decimal(value,label){
    finite(value,label);const match=String(value).match(/^(-?)(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?$/i);
    const fraction=match[3]||'',power=Number(match[4]||0)-fraction.length;
    let numerator=BigInt(match[2]+fraction)*(match[1]?-1n:1n),denominator=1n;
    if(power>=0)numerator*=10n**BigInt(power);else denominator=10n**BigInt(-power);
    return rational(numerator,denominator);
  }
  function approximate(value){
    const numerator=Number(value.n),denominator=Number(value.d);
    if(Number.isFinite(numerator)&&Number.isFinite(denominator))return numerator/denominator;
    // Tiny fractional queries may have more than 308 decimal denominator
    // digits. Rendering quantization never uses this display conversion.
    const sign=value.n<0n?-1:1,n=(value.n<0n?-value.n:value.n).toString(),d=value.d.toString();
    const a=n.slice(0,16),b=d.slice(0,16);
    return sign*Number(a)/Number(b)*10**(n.length-d.length-a.length+b.length);
  }
  function origin(recipe){
    const value=recipe.source_origin;
    if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).length!==2||typeof value.numerator!=='string'||typeof value.denominator!=='string'||!/^(0|[1-9][0-9]{0,255})$/.test(value.numerator)||!/^[1-9][0-9]{0,255}$/.test(value.denominator))throw Error('A speed ramp needs bounded nonnegative rational source-origin strings.');
    const result=rational(BigInt(value.numerator),BigInt(value.denominator));
    if(result.n>10000000n*result.d)throw Error('The source origin exceeds 10,000,000 frames.');
    return result;
  }
  function validate(recipe) {
    if(!recipe||typeof recipe!=='object'||Array.isArray(recipe)||recipe.version!==1||!['nearest','optical_flow'].includes(recipe.method)||!['varispeed','mute'].includes(recipe.audio))throw Error('Invalid speed-ramp recipe.');
    if(!Array.isArray(recipe.keys)||recipe.keys.length<2||recipe.keys.length>32)throw Error('A speed ramp needs 2–32 keys.');
    let previous=-1;
    for(const key of recipe.keys){
      if(!key||typeof key!=='object'||Array.isArray(key))throw Error('Invalid speed key.');
      const frame=integer(key.frame,'Key frame'),speed=finite(key.speed,'Key speed');
      if(frame<0||frame>240||frame<=previous)throw Error('Key frames must increase from 0 through at most 240 output frames.');
      if(speed<.25||speed>4)throw Error('Speed keys must be between 0.25× and 4×.');
      previous=frame;
    }
    if(recipe.keys[0].frame!==0)throw Error('The first speed key must be at output frame 0.');
    const offset=integer(recipe.offset,'Ramp offset');
    if(offset<0||offset>=previous)throw Error('Ramp offset is outside its authored domain.');
    origin(recipe);
    return recipe;
  }
  function at(recipe,t) {
    const keys=recipe.keys;
    if(t<=0)return keys[0].speed;
    for(let i=1;i<keys.length;i++)if(t<=keys[i].frame){const a=keys[i-1],b=keys[i];return a.speed+(b.speed-a.speed)*(t-a.frame)/(b.frame-a.frame);}
    return keys[keys.length-1].speed;
  }
  function exactIntegral(recipe,t) {
    const keys=recipe.keys;
    // Tiny audio-grid phases may lie outside an endpoint. Continuing its
    // endpoint speed preserves the absolute sample clock across a split.
    if(t.n<0n)return multiply(t,decimal(keys[0].speed,'Key speed'));
    let total=rational(0n);
    for(let i=1;i<keys.length;i++){
      const a=keys[i-1],b=keys[i],span=b.frame-a.frame;
      let part=subtract(t,rational(BigInt(a.frame)));
      if(part.n<=0n)break;
      if(compare(part,rational(BigInt(span)))>0)part=rational(BigInt(span));
      const first=decimal(a.speed,'Key speed'),last=decimal(b.speed,'Key speed');
      const quadratic=multiply(multiply(subtract(last,first),multiply(part,part)),rational(1n,BigInt(2*span)));
      total=add(total,add(multiply(first,part),quadratic));
      if(compare(t,rational(BigInt(b.frame)))<=0)return total;
    }
    const last=keys[keys.length-1],extra=subtract(t,rational(BigInt(last.frame)));
    return extra.n>0n?add(total,multiply(extra,decimal(last.speed,'Key speed'))):total;
  }
  function integral(recipe,t) {
    validate(recipe);return approximate(exactIntegral(recipe,decimal(t,'Ramp position')));
  }
  function delta(clip,t) {
    finite(t,'Local output position');
    if(!clip.retime)return t*(clip.speed??1);
    const r=validate(clip.retime),offset=rational(BigInt(r.offset));
    return approximate(subtract(exactIntegral(r,add(offset,decimal(t,'Local output position'))),exactIntegral(r,offset)));
  }
  function speed(clip,t) {
    finite(t,'Local output position');
    if(!clip.retime)return clip.speed??1;
    const r=validate(clip.retime);return at(r,r.offset+t);
  }
  function exactSource(clip,t) {
    const local=decimal(t,'Local output position');
    if(!clip.retime)return add(decimal(clip.in??0,'Source in point'),multiply(local,decimal(clip.speed??1,'Source speed')));
    const r=validate(clip.retime);
    return add(origin(r),exactIntegral(r,add(rational(BigInt(r.offset)),local)));
  }
  function sourceOrigin(clip,t=0){const value=exactSource(clip,t);return {numerator:String(value.n),denominator:String(value.d)};}
  function sourceFrame(clip,t) {return approximate(exactSource(clip,t));}
  function nearestFrame(clip,t) {
    const value=exactSource(clip,t),numerator=2n*value.n+value.d,denominator=2n*value.d;
    return Number(numerator>=0n?numerator/denominator:-((-numerator+denominator-1n)/denominator));
  }
  function slice(clip,offset) {
    const r=validate(clip.retime);integer(offset,'Slice offset');
    if(r.offset+offset<0||r.offset+offset>r.keys[r.keys.length-1].frame)throw Error('The edit is outside the speed ramp domain.');
    return {in:sourceFrame(clip,offset),retime:{...copy(r),offset:r.offset+offset}};
  }
  function trim(clip,edge,requested,max=Infinity) {
    const r=validate(clip.retime);integer(clip.duration,'Clip duration');integer(clip.start,'Clip start');finite(requested,'Trim position');
    if(clip.duration<1||r.offset+clip.duration>r.keys[r.keys.length-1].frame)throw Error('The clip extends beyond its speed ramp domain.');
    if(max!==Infinity&&(!Number.isFinite(max)||max<0))throw Error('Source length is invalid.');
    const bounded=(value,low,high)=>Math.max(low,Math.min(high,value));
    if(edge==='left'){
      let low=Math.max(-clip.start,-r.offset),high=0;
      // Positive speed makes the source mapping monotonic; find the earliest
      // legal whole-frame extension without changing the original curve.
      while(low<high){const middle=Math.floor((low+high)/2);if(sourceFrame(clip,middle)>=-1e-9)high=middle;else low=middle+1;}
      const shift=bounded(Math.round(requested-clip.start),low,clip.duration-1),next=slice(clip,shift);
      return {start:clip.start+shift,duration:clip.duration-shift,...next,offset:shift};
    }
    if(edge!=='right')throw Error('Choose the left or right clip edge.');
    let low=0,high=r.keys[r.keys.length-1].frame-r.offset;
    while(low<high){const middle=Math.ceil((low+high)/2);if(sourceFrame(clip,middle)<=max+1e-9)low=middle;else high=middle-1;}
    if(low<1)throw Error('No complete ramp frame remains inside this source.');
    const duration=bounded(Math.round(requested-clip.start),1,low);
    return {start:clip.start,duration,...slice(clip,0),offset:0};
  }
  function localKeys(clip) {
    const r=validate(clip.retime),duration=integer(clip.duration,'Clip duration');
    if(duration<1||r.offset+duration>r.keys[r.keys.length-1].frame)throw Error('The clip extends beyond its speed ramp domain.');
    return [{frame:0,speed:speed(clip,0)},...r.keys.filter(k=>k.frame>r.offset&&k.frame<r.offset+duration).map(k=>({frame:k.frame-r.offset,speed:k.speed})),{frame:duration,speed:speed(clip,duration)}];
  }
  window.CinematicumRetimeModel={validate,integral,delta,speed,sourceOrigin,sourceFrame,nearestFrame,trim,slice,localKeys};
})();
