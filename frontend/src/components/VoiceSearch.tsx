import {useEffect,useRef,useState} from 'react'
import {Mic,Square,X} from 'lucide-react'
import {api,humanError} from '../lib/api'

// PCM WAV capture uses only the microphone and Web Audio. Browser speech
// recognition services are deliberately not used: they may send audio off-device.
export default function VoiceSearch({disabled,onTranscript,onActivity}:{disabled:boolean;onTranscript:(text:string)=>void;onActivity:(active:boolean)=>void}){
 const [state,setState]=useState<'idle'|'requesting'|'recording'|'transcribing'>('idle'),[error,setError]=useState(''),[seconds,setSeconds]=useState(0)
 const capture=useRef<{stream:MediaStream;context:AudioContext;node:ScriptProcessorNode;source:MediaStreamAudioSourceNode;gain:GainNode;chunks:Float32Array[]}|null>(null)
 const timer=useRef<ReturnType<typeof setInterval>|undefined>(undefined),mounted=useRef(true),version=useRef(0)
 function release(){clearInterval(timer.current);const c=capture.current;capture.current=null;if(c){c.node.onaudioprocess=null;c.node.disconnect();c.source.disconnect();c.gain.disconnect();c.stream.getTracks().forEach(t=>t.stop());void c.context.close()}return c}
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;version.current++;release()}},[])
 function cancel(){version.current++;release();setState('idle');setSeconds(0);onActivity(false)}
 async function start(){
  const token=++version.current;setError('');setState('requesting');setSeconds(0);onActivity(true)
  try{
   if(!navigator.mediaDevices?.getUserMedia)throw new Error('Microphone access requires this app to be opened on localhost.')
   const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}})
   if(!mounted.current||version.current!==token){stream.getTracks().forEach(t=>t.stop());return}
   const context=new AudioContext(),source=context.createMediaStreamSource(stream),node=context.createScriptProcessor(4096,1,1),gain=context.createGain();gain.gain.value=0
   capture.current={stream,context,node,source,gain,chunks:[]};node.onaudioprocess=e=>capture.current?.chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)))
   source.connect(node);node.connect(gain);gain.connect(context.destination);await context.resume();setState('recording');let elapsed=0
   timer.current=setInterval(()=>{elapsed++;setSeconds(elapsed);if(elapsed>=45)void stop()},1000)
  }catch(e){release();if(mounted.current&&version.current===token){setError(e instanceof DOMException&&e.name==='NotAllowedError'?'Microphone access was denied. Allow it in browser settings or type your question.':humanError(e));setState('idle');onActivity(false)}}
 }
 async function stop(){
  const c=release();if(!c)return;const token=version.current;setState('transcribing');setError('')
  try{
   const length=c.chunks.reduce((n,x)=>n+x.length,0),input=new Float32Array(length);let cursor=0;for(const chunk of c.chunks){input.set(chunk,cursor);cursor+=chunk.length}
   const count=Math.floor(length*16000/c.context.sampleRate);if(count<4000)throw new Error('Please speak for at least a moment, then stop.')
   const buffer=new ArrayBuffer(44+count*2),view=new DataView(buffer),str=(at:number,s:string)=>{for(let i=0;i<s.length;i++)view.setUint8(at+i,s.charCodeAt(i))}
   str(0,'RIFF');view.setUint32(4,36+count*2,true);str(8,'WAVE');str(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,16000,true);view.setUint32(28,32000,true);view.setUint16(32,2,true);view.setUint16(34,16,true);str(36,'data');view.setUint32(40,count*2,true)
   for(let i=0;i<count;i++){const at=i*c.context.sampleRate/16000,left=Math.floor(at),f=at-left,sample=Math.max(-1,Math.min(1,(input[left]||0)*(1-f)+(input[left+1]||0)*f));view.setInt16(44+i*2,sample<0?sample*32768:sample*32767,true)}
   const form=new FormData();form.append('audio',new Blob([buffer],{type:'audio/wav'}),'search.wav')
   const response=await api.post<{transcript:string}>('/assistant/transcribe',form,{headers:{'Content-Type':'multipart/form-data'},timeout:310000})
   if(mounted.current&&version.current===token)onTranscript(response.data.transcript)
  }catch(e){if(mounted.current&&version.current===token)setError(humanError(e))}finally{if(mounted.current&&version.current===token){setState('idle');onActivity(false)}}
 }
 const recording=state==='recording'
 return <div className="voice-search-control"><button type="button" className={`voice-search-button ${recording?'is-recording':''}`} aria-label={recording?'Stop recording':state==='transcribing'?'Transcribing on this computer':'Speak your question'} title="Speak your question · offline transcription" disabled={disabled||state==='transcribing'||state==='requesting'} onClick={()=>recording?void stop():void start()}>{recording?<Square size={18}/>:<Mic size={20}/>}</button>{state!=='idle'&&<div className="voice-search-status" role="status">{recording?`Listening · ${seconds}s / 45s`:state==='requesting'?'Allow microphone access…':'Transcribing locally…'}<button type="button" aria-label="Cancel voice input" onClick={cancel}><X size={15}/></button></div>}{error&&<p className="voice-search-error" role="alert">{error}</p>}</div>
}
