// Test-only render-thread capture. The native harness serves this exact file;
// it is never referenced or loaded by the production application.
class CinematicumAudioProbe extends AudioWorkletProcessor{
  constructor(){
    super();this.start=-1;this.actualStart=-1;this.count=0;this.done=false;
    this.size=8192;this.samples=null;
    this.port.onmessage=event=>{if(event.data?.action==='capture'&&(this.start<0||this.done)){
      this.start=Number(event.data.start_frame);this.actualStart=-1;this.count=0;this.done=false;
      const count=event.data.sample_count;this.size=Number.isInteger(count)&&count>=8192&&count<=65536?count:8192;
      this.samples=Array.from({length:3},()=>[new Float32Array(this.size),new Float32Array(this.size)]);
    }};
  }
  process(inputs,outputs){
    for(const output of outputs)for(const channel of output)channel.fill(0);
    if(this.start<0||this.done)return true;
    const length=outputs[0]?.[0]?.length||128;
    for(let frame=0;frame<length&&this.count<this.size;frame++){
      if(currentFrame+frame<this.start)continue;
      if(this.actualStart<0)this.actualStart=currentFrame+frame;
      for(let input=0;input<3;input++)for(let channel=0;channel<2;channel++)this.samples[input][channel][this.count]=inputs[input]?.[channel]?.[frame]??0;
      this.count++;
    }
    if(this.count===this.size){
      this.done=true;
      this.port.postMessage({samples:this.samples,start_frame:this.actualStart,end_frame:this.actualStart+this.size,requested_start_frame:this.start,sample_rate:sampleRate},this.samples.flat().map(channel=>channel.buffer));
    }
    return true;
  }
}
registerProcessor('cinematicum-audio-probe',CinematicumAudioProbe);
