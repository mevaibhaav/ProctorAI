import axios from 'axios';
export const api=axios.create({baseURL:import.meta.env.VITE_API_URL||'http://127.0.0.1:8000/api'});
api.interceptors.request.use(config=>{const token=localStorage.getItem('proctorai-token');if(token)config.headers.Authorization=`Bearer ${token}`;return config;});
// Attach a single, transient camera frame to each logged incident. The API
// stores it locally for administrator review; no continuous video is sent.
api.interceptors.response.use(response=>{
  if(response.config.method==='post'&&response.config.url?.replace(/^.*\/api/, '').replace(/^.*\/proctoring/, '/proctoring')==='/proctoring/events'&&response.data?.id&&typeof document!=='undefined'){
    const video=document.querySelector('.camera-view video') as HTMLVideoElement|null;
    if(video&&video.readyState>=2){
      const canvas=document.createElement('canvas');canvas.width=320;canvas.height=240;
      canvas.getContext('2d')?.drawImage(video,0,0,canvas.width,canvas.height);
      canvas.toBlob(blob=>{if(blob){const form=new FormData();form.append('photo',blob,'incident.jpg');api.post(`/proctoring/events/${response.data.id}/snapshot`,form).catch(()=>{});}},'image/jpeg',.72);
    }
  }
  return response;
});
// Keep an exam marked live only while its taking page remains open. The server
// expires presence after 30 seconds without a heartbeat (e.g. a closed tab).
if (typeof window !== 'undefined') window.setInterval(()=>{
  const match=window.location.pathname.match(/^\/app\/take\/(\d+)/);
  const attemptId=localStorage.getItem('proctorai-attempt');
  if(match&&attemptId&&match[1]===attemptId) api.post(`/attempts/${encodeURIComponent(attemptId)}/heartbeat`).catch(()=>{});
},8000);
export function saveSession(token:string,user:any){localStorage.setItem('proctorai-token',token);localStorage.setItem('proctorai-user',JSON.stringify(user));}
export function clearSession(){localStorage.removeItem('proctorai-token');localStorage.removeItem('proctorai-user');}
