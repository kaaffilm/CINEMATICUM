// Async-function body for SmokeTest.swift. Python supplies CAMERA_IMPORT_TEST.
// All mutations use shipped DOM controls and real FileLists in native WebKit.
return await (async()=>{
  const began=performance.now(),deadline=began+11500,steps=[],modalLayouts=[],$=s=>document.querySelector(s),all=s=>[...document.querySelectorAll(s)];
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const diagnostic=()=>'; camera='+($('[data-camera-status]')?.textContent||'')+'; toast='+($('#toast')?.textContent||'');
  async function until(predicate,label,ms=1800){const end=Math.min(deadline,performance.now()+ms);while(performance.now()<end){if(predicate())return;await sleep(30);}throw Error(label+diagnostic());}
  function visibleCameraControls(){const dialog=$('.cinematicum-camera-io');if(!dialog?.open)return;const bounds=dialog.getBoundingClientRect();for(const control of all('[data-camera-review],[data-camera-apply],[data-camera-close]')){if(control.hidden)continue;const rect=control.getBoundingClientRect(),x=rect.left+rect.width/2,y=rect.top+rect.height/2,hit=document.elementFromPoint(x,y);if(rect.width<20||rect.height<20||rect.left<Math.max(0,bounds.left)-1||rect.right>Math.min(innerWidth,bounds.right)+1||rect.top<Math.max(0,bounds.top)-1||rect.bottom>Math.min(innerHeight,bounds.bottom)+1||!(hit===control||control.contains(hit)))throw Error('Camera action is clipped or not pointer reachable: '+control.textContent.trim());}}
  function checkCameraLayout(){const body=$('.camera-io-body'),dialog=$('.cinematicum-camera-io'),footer=$('.camera-io-footer'),before=body.scrollTop;visibleCameraControls();body.scrollTop=0;visibleCameraControls();body.scrollTop=body.scrollHeight;visibleCameraControls();if(body.scrollHeight>body.clientHeight+2&&body.scrollTop<1)throw Error('Camera content cannot scroll to its final fields.');const b=body.getBoundingClientRect(),f=footer.getBoundingClientRect();if(b.bottom>f.top+1)throw Error('Camera body covers its fixed action footer.');body.scrollTop=before;const d=dialog.getBoundingClientRect();modalLayouts.push({viewport:[innerWidth,innerHeight],dialog:[d.x,d.y,d.width,d.height],body_client_height:body.clientHeight,body_scroll_height:body.scrollHeight,footer:[f.x,f.y,f.width,f.height]});}
  function click(s){const e=$(s);if(!e||e.disabled)throw Error('Unavailable control '+s+diagnostic());if(e.matches('[data-camera-review],[data-camera-apply],[data-camera-close]'))visibleCameraControls();e.click();}
  function set(s,value){const e=$(s);if(!e||e.disabled)throw Error('Unavailable field '+s);e.value=String(value);e.dispatchEvent(new Event('change',{bubbles:true}));}
  function files(items){const transfer=new DataTransfer();for(const item of items){const data=item.base64?Uint8Array.from(atob(item.base64),c=>c.charCodeAt(0)):item.text;transfer.items.add(new File([data],item.name,{type:item.base64?'application/octet-stream':'text/plain'}));}const input=$('[data-camera-files]');input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));}
  const cameraKeys=()=>all('.scene-key-lane[data-track-id="camera"] .scene-key:not(.implicit)').length;
  const prop=name=>Number($('[data-scene-property="'+name+'"]')?.value);
  const cameraSelected=()=>click('.scene-object-list [data-scene-select="camera"]');
  function checkCamera(expected){cameraSelected();for(const name of ['fov','roll','shift_x','shift_y','focal_ratio']){const tolerance=['fov','roll'].includes(name)?.0051:.000051;if(Math.abs(prop(name)-expected[name])>tolerance)throw Error('Displayed camera '+name+' differs from imported projection: '+prop(name)+' vs '+expected[name]);}}
  // Inspector fields intentionally display two decimals for FOV/roll and four
  // for shifts/ratio. The Python harness still compares saved numbers exactly;
  // source-to-Blender projection acceptance retains its independent tolerance.
  try{
    await until(()=>$('#viewer-project')?.textContent.includes('ENGINE TEST')&&$('#project-select')?.value,'Test project did not bootstrap',4500);
    click('[data-mode="3d"]');await until(()=>$('.scene-viewport canvas')?.getBoundingClientRect().width>100,'3D workspace did not mount');
    cameraSelected();if(cameraKeys()!==2||prop('roll')!==12)throw Error('Expected the original keyed fixture camera.');
    click('[data-scene-action="import-camera"]');await until(()=>$('.cinematicum-camera-io')?.open,'Camera dialog did not open');
    files([{name:'ENGINE_TEST_duplicate.json',text:'{"cameraParameters":null,"cameraParameters":null}'}]);click('[data-camera-review]');
    await until(()=>!$('[data-camera-review]').disabled&&$('[data-camera-status]').textContent.includes('Duplicate JSON member'),'The backend did not reject original duplicate JSON');
    if(!$('[data-camera-result]').hidden||!$('#undo-button').disabled||cameraKeys()!==2)throw Error('A rejected import changed the scene or history.');
    steps.push('reject_original_duplicate_json_without_history');
    files([{name:'ENGINE_TEST_camera.fspy',base64:CAMERA_IMPORT_TEST.fspy_base64}]);click('[data-camera-review]');
    await until(()=>!$('[data-camera-result]').hidden&&!$('[data-camera-review]').disabled,'Binary fSpy camera review failed',2200);
    if($('[data-camera-replace-notice]').hidden||!$('[data-camera-replace-notice]').textContent.includes('all of its animation keys'))throw Error('Replacing camera animation was not disclosed.');
    checkCameraLayout();steps.push('camera_actions_visible_with_scrollable_review');
    if(!$('#undo-button').disabled||cameraKeys()!==2)throw Error('Camera review applied or checkpointed the scene.');
    click('[data-camera-apply]');await until(()=>!$('.cinematicum-camera-io').open,'fSpy camera apply failed');
    checkCamera(CAMERA_IMPORT_TEST.fspy_camera);if(cameraKeys()!==0)throw Error('Imported camera retained unrelated animation keys.');
    click('#undo-button');cameraSelected();if(cameraKeys()!==2||prop('roll')!==12||!$('#undo-button').disabled)throw Error('Camera import did not undo as one complete camera replacement.');
    click('#redo-button');checkCamera(CAMERA_IMPORT_TEST.fspy_camera);if(cameraKeys()!==0)throw Error('Redo did not restore the calibrated camera.');
    steps.push('native_binary_fspy_input_apply_undo_redo');
    click('#undo-button');cameraSelected();
    click('[data-scene-action="import-camera"]');set('[data-camera-format]','colmap');
    files([{name:'images.txt',text:CAMERA_IMPORT_TEST.colmap.images_text},{name:'cameras.txt',text:CAMERA_IMPORT_TEST.colmap.cameras_text}]);click('[data-camera-review]');
    await until(()=>!$('[data-camera-result]').hidden&&!$('[data-camera-review]').disabled,'COLMAP paired file review failed',2200);
    checkCameraLayout();
    if(all('[data-camera-choice] option').length!==2)throw Error('Registered camera pose choices are missing.');
    set('[data-camera-choice]','93');click('[data-camera-apply]');await until(()=>!$('.cinematicum-camera-io').open,'Selected COLMAP camera did not apply');
    checkCamera(CAMERA_IMPORT_TEST.colmap_camera);if(cameraKeys()!==0||$('#save-state').textContent!=='UNSAVED')throw Error('Camera replacement must clear keys and remain unsaved.');
    click('#undo-button');cameraSelected();if(cameraKeys()!==2||prop('roll')!==12)throw Error('COLMAP apply did not undo back to the original keyed camera.');
    click('#redo-button');checkCamera(CAMERA_IMPORT_TEST.colmap_camera);
    steps.push('native_colmap_pair_pose_selection_and_single_undo');
    click('#save-project');await until(()=>$('#save-state').textContent==='SAVED LOCALLY','Calibrated camera could not be saved',2200);
    steps.push('save_calibration_with_unrelated_scene_preserved');
    // Leave a reviewed, unapplied camera dialog visible for the native image.
    click('[data-scene-action="import-camera"]');set('[data-camera-format]','fspy');
    files([{name:'ENGINE_TEST_camera.fspy',base64:CAMERA_IMPORT_TEST.fspy_base64}]);click('[data-camera-review]');
    await until(()=>!$('[data-camera-result]').hidden&&!$('[data-camera-review]').disabled,'Final review could not be displayed');
    checkCameraLayout();
    if($('#save-state').textContent!=='SAVED LOCALLY')throw Error('Read-only review dirtied the saved scene.');
    return {passed:true,steps,modal_layouts:modalLayouts,project_id:$('#project-select').value,selected_pose_id:'93',elapsed_ms:Math.round(performance.now()-began)};
  }catch(error){return {passed:false,steps,modal_layouts:modalLayouts,error:String(error),camera_status:$('[data-camera-status]')?.textContent||'',camera_keys:cameraKeys(),elapsed_ms:Math.round(performance.now()-began)};}
})();
