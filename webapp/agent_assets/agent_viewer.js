import { captureThumbnail } from '/webgpu/capture.js';
const root=location.pathname.replace(/\/$/,''),status=document.querySelector('#status'),progress=document.querySelector('#progress'),retry=document.querySelector('#retry');
document.querySelector('#pattern').src=root+'/pattern.png';
for(const [id,asset] of [['svg-link','pattern.svg'],['png-link','pattern.png']])document.getElementById(id).href=root+'/'+asset;
async function render(){
  retry.hidden=true;progress.hidden=false;
  try{
    const infoResponse=await fetch(root+'/status');if(!infoResponse.ok)throw Error('This render has expired. Request a new render from your agent.');
    const info=await infoResponse.json();
    if(!info.has_scene){status.textContent='2D pattern ready.';progress.hidden=true;return;}
    if(info.state==='ready_3d'){
      const canvas=document.querySelector('#render'),image=document.createElement('img');image.src=root+'/thumbnail.webp';image.alt='3D garment on the default mannequin';canvas.replaceWith(image);
      status.textContent='3D render saved to your library.';progress.hidden=true;return;
    }
    if(!navigator.gpu)throw Error('3D needs a browser with WebGPU. The 2D pattern is ready to download.');
    status.textContent='Draping in your browser…';
    const response=await fetch(root+'/scene.json');if(!response.ok)throw Error('Could not load the 3D scene.');
    const image=await captureThumbnail(await response.json(),document.querySelector('#render'),frame=>{progress.value=frame;});
    status.textContent='Saving render…';
    const saved=await fetch(root+'/complete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image})});
    if(!saved.ok){const error=await saved.json();throw Error(error.detail || 'Could not save the render.');}
    const preview=document.createElement('img');preview.src=image;preview.alt='3D garment on the default mannequin';
    document.querySelector('#render').replaceWith(preview);
    status.textContent='3D render saved to your library.';document.body.dataset.renderState='ready';progress.hidden=true;
  }catch(error){
    status.textContent=error.message;document.body.dataset.renderState='failed';progress.hidden=true;retry.hidden=false;
    fetch(root+'/failed',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({error:error.message})}).catch(()=>{});
  }
}
retry.addEventListener('click',render);render();
