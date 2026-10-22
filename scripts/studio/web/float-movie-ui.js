/* Color-managed movie settings use the project's ordinary undo/save history. */
(() => {
  'use strict';
  const defaults={version:1,config:'studio-config-v5.0.0_aces-v2.1_ocio-v2.6',working_space:'ACEScg',output_space:'ACEScg',default_input_space:'Camera Rec.709',display:'sRGB - Display',view:'ACES 2.0 - SDR 100 nits (Rec.709)'};
  function mount(host,{request,getProject,edit,toast}) {
    let catalog=null,pending=null,serial=0;
    host.style.maxHeight='40vh';host.style.overflowY='auto';
    function label(text){const element=document.createElement('label');element.textContent=text;return element;}
    function select(name,value,items,onChange){
      const control=document.createElement('select');control.dataset.floatSetting=name;
      for(const item of items){const option=document.createElement('option');option.value=typeof item==='string'?item:item.value;option.textContent=typeof item==='string'?item:item.label;control.append(option);}
      if(![...control.options].some(option=>option.value===value)){const option=document.createElement('option');option.value=value;option.textContent=value+' · unavailable';control.append(option);}
      control.value=value;control.addEventListener('change',()=>{onChange(control.value);render();});return control;
    }
    function render(){
      const project=getProject(),active=project?.settings?.image_precision==='float32';host.hidden=!active;
      if(!active)return;
      host.replaceChildren();
      if(!catalog){const p=document.createElement('p');p.className='muted';p.textContent='Checking the local float imaging runtime…';host.append(p);load();return;}
      if(!catalog.available){const p=document.createElement('p');p.className='error';p.textContent=catalog.reason||'Install the Imaging runtime to process float movies.';host.append(p);return;}
      const color={...defaults,...project.settings.float_color};
      const info=document.createElement('p');info.className='muted';info.textContent='ACES 2.1 / OCIO · Float32 scene-linear processing. The master preserves negative and superwhite values. Preview uses the selected SDR view; display calibration and HDR monitoring are not provided.';host.append(info);
      for(const [field,title,items]of [['working_space','Working space',catalog.working_spaces],['output_space','EXR master space',catalog.working_spaces],['default_input_space','Default source interpretation',catalog.color_spaces],['view','Preview display view',catalog.views]]){
        const row=label(title),control=select(field,color[field],items,value=>edit(p=>{p.settings.float_color={...defaults,...p.settings.float_color,[field]:value};}));row.append(control);host.append(row);
      }
      const heading=document.createElement('h4');heading.textContent='Source color interpretations';host.append(heading);
      for(const clip of project.clips.filter(c=>c.track>=0&&!c.sequence_id)){
        const asset=project.assets.find(a=>a.id===clip.asset_id);if(!asset)continue;
        const row=label(asset.name+' · '+clip.id.slice(0,8));
        const choices=[{value:'',label:'Use default: '+color.default_input_space},...catalog.color_spaces];
        const control=select('input-'+clip.id,clip.float_input_space||'',choices,value=>edit(p=>{const current=p.clips.find(c=>c.id===clip.id);if(!current)return;if(value)current.float_input_space=value;else delete current.float_input_space;}));
        control.dataset.floatClip=clip.id;row.append(control);host.append(row);
      }
      const note=document.createElement('p');note.className='muted';note.textContent='EXR and PQ/HLG clips require an explicit source space. V1 supports transforms, opacity animation, exposure, raster titles and the existing audio mixer. Unsupported SDR effects, graphs and live nested sequences refuse rendering.';host.append(note);
    }
    async function load(){
      if(catalog||pending)return pending;
      const requestSerial=++serial;
      pending=request('/api/float-movie-capabilities').then(value=>{if(requestSerial===serial)catalog=value;}).catch(error=>{catalog={available:false,reason:error.message};toast(error.message,true);}).finally(()=>{pending=null;render();});return pending;
    }
    return {render,load,defaults,reset(){serial++;catalog=null;pending=null;render();}};
  }
  window.CinematicumFloatMovie={mount,defaults};
})();
