"""whisper.cpp subprocess adapter. No SDK, network, cache or download fallback."""
from pathlib import Path
from threading import Lock
import io
import json
import subprocess
import tempfile
import wave
from array import array
import sys
from app.core.config import settings

ROOT=Path(__file__).resolve().parents[3]
_inference_lock=Lock()


def asset_path(value):
    p=Path(value).expanduser()
    return p.resolve() if p.is_absolute() else (ROOT/p).resolve()


def speech_assets():
    exe=asset_path(settings.whisper_cpp_executable);model=asset_path(settings.whisper_cpp_model)
    return exe,model


def transcribe(audio,suffix):
    from app.ai.local_models import LocalModelError
    exe,model=speech_assets()
    if not exe.is_file() or not model.is_file():
        raise LocalModelError('whisper.cpp is not installed. Prepare whisper-cli and ggml-base.bin locally before using voice input. No download was attempted.')
    if not _inference_lock.acquire(blocking=False):
        raise LocalModelError('Another local transcription is running. Please try again when it finishes.')
    try:
        with tempfile.TemporaryDirectory(prefix='advicue-speech-') as temp:
            folder=Path(temp);source=folder/('recording'+suffix);source.write_bytes(audio);wav=folder/'input.wav'
            try:
                with wave.open(io.BytesIO(audio),'rb') as w:
                    pcm=(w.getcomptype()=='NONE' and w.getnchannels()==1 and w.getframerate()==16000 and w.getsampwidth()==2)
                    duration=w.getnframes()/w.getframerate()
                    convertible=w.getcomptype()=='NONE' and w.getnchannels() in (1,2) and w.getsampwidth()==2 and 8000<=w.getframerate()<=96000
                    if not pcm and convertible:
                        channels=w.getnchannels();rate=w.getframerate();samples=array('h',w.readframes(w.getnframes()))
                        if sys.byteorder!='little':samples.byteswap()
                if duration>300:raise LocalModelError('Recordings must be at most five minutes. Split longer meetings into sections.')
            except (wave.Error,EOFError):pcm=False;convertible=False
            if pcm:wav.write_bytes(audio)
            elif convertible:
                frames=len(samples)//channels;mono=array('f',(sum(samples[i*channels:(i+1)*channels])/channels for i in range(frames)))
                normalized=array('h')
                for i in range(int(frames*16000/rate)):
                    at=i*rate/16000;left=int(at);fraction=at-left
                    normalized.append(round(mono[left]*(1-fraction)+mono[min(left+1,frames-1)]*fraction))
                if sys.byteorder!='little':normalized.byteswap()
                with wave.open(str(wav),'wb') as w:w.setparams((1,2,16000,0,'NONE','not compressed'));w.writeframes(normalized.tobytes())
            else:
                ffmpeg=asset_path(settings.local_ffmpeg)
                if not ffmpeg.is_file():raise LocalModelError('Use a 16 kHz mono PCM WAV recording, or install the local FFmpeg executable for other formats.')
                # File input and output are generated paths. Disable all network protocols.
                converted=subprocess.run([str(ffmpeg),'-nostdin','-v','error','-protocol_whitelist','file,pipe','-i',str(source),'-t','301','-ar','16000','-ac','1','-c:a','pcm_s16le',str(wav)],capture_output=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if converted.returncode:raise LocalModelError('The local audio decoder could not read this recording.')
                with wave.open(str(wav),'rb') as w:
                    if w.getnframes()/w.getframerate()>300:raise LocalModelError('Recordings must be at most five minutes. No partial transcript was saved.')
            output=folder/'transcript'
            run=subprocess.run([str(exe),'-m',str(model),'-f',str(wav),'-l','auto','-t','4','-ng','-oj','-of',str(output)],cwd=str(exe.parent),capture_output=True,timeout=300,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if run.returncode or not output.with_suffix('.json').is_file():raise LocalModelError('whisper.cpp could not transcribe this recording. Check the locally installed model and runtime.')
            result=json.loads(output.with_suffix('.json').read_text(encoding='utf-8'))
            text=' '.join(x.get('text','').strip() for x in result.get('transcription',[]) if isinstance(x,dict)).strip()
            if not text or text in ('[BLANK_AUDIO]','[ Silence ]'):raise LocalModelError('No speech detected. Please try again.')
            if len(text)>30000:raise LocalModelError('The transcript exceeds the note limit. Split the recording into shorter sections.')
            return text
    except LocalModelError:raise
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        raise LocalModelError('Local transcription failed. Verify the installed whisper.cpp assets. No download was attempted.') from exc
    finally:_inference_lock.release()
