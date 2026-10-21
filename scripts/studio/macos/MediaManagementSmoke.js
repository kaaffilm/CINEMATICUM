// Real WKWebView media-management controls. Only public synthetic fixture
// bytes are supplied by Python. Decoder observation returns the original
// browser video elements unchanged; it never substitutes decoding or HTTP.
return await(async()=>{
  const began=performance.now(),steps=[],metrics={},$=selector=>document.querySelector(selector);
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const panel='.media-management-dialog',q=selector=>$(panel+' '+selector);
  const diagnostic=()=>'; media='+(q('[data-status]')?.textContent||'')+'; job='+($('#job-label')?.textContent||'')+' / '+($('#job-detail')?.textContent||'')+'; toast='+($('#toast')?.textContent||'');
  async function until(predicate,label,maximum=2500){const end=performance.now()+maximum;while(performance.now()<end){if(predicate())return;await sleep(25);}throw Error(label+diagnostic());}
  function reach(selector){const element=$(selector);if(!element||element.disabled||element.hidden)throw Error('Unavailable '+selector+diagnostic());const r=element.getBoundingClientRect(),hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);if(r.width<2||r.height<2||r.left<0||r.top<0||r.right>innerWidth+.5||r.bottom>innerHeight+.5||(hit!==element&&!element.contains(hit)))throw Error('Unreachable '+selector);return element;}
  function click(selector){reach(selector).click();}
  function set(selector,value){const element=reach(selector);if(element.type==='checkbox')element.checked=value;else element.value=String(value);element.dispatchEvent(new Event('change',{bubbles:true}));}
  async function open(){click('#media-management-button');await until(()=>$(panel)?.open&&q('[data-source]').options.length===1&&q('[data-status]').textContent==='','Media inventory did not open');}
  function close(){click(panel+' [data-close]');}
  async function save(){click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY'&&!$('#save-project').disabled,'Actual media settings did not save');}
  async function render(){const previous=$('#download-job')?.getAttribute('href');click('#export-button');click('[data-export="prores"]');await until(()=>$('#job-label').textContent==='ProRes export complete'&&!$('#download-job').hidden&&$('#download-job').getAttribute('href')!==previous,'Actual original-source ProRes export failed',4000);metrics.movie=$('#download-job').getAttribute('href');steps.push('actual_prores_export_control');}
  const nativeCreate=document.createElement,observed=[];
  document.createElement=function(name,...options){const element=Reflect.apply(nativeCreate,this,[name,...options]);if(String(name).toLowerCase()==='video')observed.push(element);return element;};
  const matches=(element,kind)=>{const source=element.currentSrc||element.src;if(!source)return false;const url=new URL(source,location.href);return url.origin===location.origin&&url.pathname==='/api/projects/'+MEDIA_TEST.project_id+'/'+(kind==='proxy'?'media-proxy/':'media/')+MEDIA_TEST.asset_id;};
  async function decoder(kind,width){await until(()=>observed.some(element=>matches(element,kind)&&element.readyState>=2&&element.videoWidth===width),'The actual '+kind+' video decoder did not load',3000);const element=observed.findLast(element=>matches(element,kind)&&element.readyState>=2&&element.videoWidth===width),url=new URL(element.currentSrc||element.src,location.href),canvas=nativeCreate.call(document,'canvas');canvas.width=80;canvas.height=45;const context=canvas.getContext('2d');context.drawImage(element,0,0,80,45);const data=context.getImageData(0,0,80,45).data;let changed=0;for(let i=0;i<data.length;i+=4)if(Math.max(data[i],data[i+1],data[i+2])>50)changed++;if(changed<500)throw Error('Actual '+kind+' decoder produced no synthetic test picture');return {url:url.pathname+url.search,width:element.videoWidth,height:element.videoHeight,ready_state:element.readyState,nonblack_pixels:changed};}
  function chooseFile(bytes,name){const transfer=new DataTransfer();transfer.items.add(new File([bytes],name,{type:'video/mp4'}));const input=q('[data-file]');input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));}
  try{
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST media management')&&$('.timeline-clip[data-type="clip"]')&&$('#media-management-button'),'Media-management fixture did not bootstrap',3500);
    if($('#project-select').value!==MEDIA_TEST.project_id)throw Error('Unexpected project selected');
    const stage=MEDIA_TEST.stage;
    if(stage==='baseline'){
      await open();if(!q('[data-description]').textContent.includes('Original is present.')||q('[data-enabled]').checked)throw Error('Baseline requires the exact original without preview proxies');
      metrics.original_decoder=await decoder('original',800);close();await save();await render();
      steps.push('actual_original_browser_decoder');
    }else if(stage==='cancel'){
      await open();set(panel+' [data-edge]',960);click(panel+' [data-build]');
      await until(()=>!q('[data-cancel]').hidden&&q('[data-status]').textContent.includes('Encoding'),'Proxy did not begin its actual owned job',2000);
      click(panel+' [data-cancel]');await until(()=>q('[data-cancel]').hidden&&!q('[data-build]').disabled&&/cancelled/i.test(q('[data-status]').textContent),'Proxy cancellation did not reach a terminal state',3000);
      if(!q('[data-description]').textContent.includes('No proxy'))throw Error('Canceled proxy was admitted');
      metrics.cancel_status=q('[data-status]').textContent;steps.push('real_proxy_job_cancel_control');close();await save();
    }else if(stage==='proxy'){
      await open();set(panel+' [data-edge]',640);metrics.original_decoder=await decoder('original',800);
      click(panel+' [data-build]');await until(()=>q('[data-cancel]').hidden&&!q('[data-build]').disabled&&q('[data-status]').textContent.startsWith('Proxy ready'),'Proxy did not encode and verify actual media',5000);
      if(!q('[data-description]').textContent.includes('640 × 360')||!q('[data-description]').textContent.includes('60 pictures'))throw Error('Verified proxy dimensions/frame count are missing');
      set(panel+' [data-enabled]',true);metrics.proxy_decoder=await decoder('proxy',640);
      if(!metrics.proxy_decoder.url.endsWith('?long_edge=640')||metrics.proxy_decoder.url===metrics.original_decoder.url)throw Error('Preview did not switch to its actual proxy URL');
      steps.push('real_proxy_encoding_and_timestamp_verification','preview_toggle_switches_actual_decoder_url');close();await save();await render();
    }else if(stage==='relink'){
      await open();if(!q('[data-description]').textContent.includes('Original is missing.')||!q('[data-build]').disabled)throw Error('Removed owned original was not reported missing');
      reach(panel+' [data-relink]');
      chooseFile(new Uint8Array([69,78,71,73,78,69,32,84,69,83,84]),'ENGINE_TEST_wrong_original.mp4');
      await until(()=>q('[data-status]').textContent.includes('SHA-256')&&!q('[data-relink]').disabled,'Different file was not rejected by byte identity');
      click(panel+' [data-refresh]');await until(()=>q('[data-description]').textContent.includes('Original is missing.'),'Wrong upload changed original inventory');
      const bytes=Uint8Array.from(atob(MEDIA_TEST.original_base64),character=>character.charCodeAt(0));chooseFile(bytes,'ENGINE_TEST_exact_original.mp4');
      await until(()=>q('[data-status]').textContent==='Original restored; edit and asset identity retained.'&&!q('[data-relink]').disabled,'Exact File upload did not restore the original',3500);
      if(!q('[data-description]').textContent.includes('Original is present.'))throw Error('Relink did not restore the inventory');
      set(panel+' [data-enabled]',false);metrics.restored_original_decoder=await decoder('original',800);
      set(panel+' [data-enabled]',true);metrics.restored_proxy_decoder=await decoder('proxy',640);
      steps.push('missing_original_visible','wrong_browser_file_rejected','exact_browser_file_restores_original','restored_original_and_proxy_decode');close();await save();await render();
    }else throw Error('Unknown native media-management stage');
    return {passed:true,stage,steps,metrics,elapsed_ms:Math.round(performance.now()-began)};
  }catch(error){return {passed:false,stage:MEDIA_TEST.stage,steps,metrics,error:String(error),media_status:q('[data-status]')?.textContent,toast:$('#toast')?.textContent,elapsed_ms:Math.round(performance.now()-began)};}
  finally{document.createElement=nativeCreate;}
})();
