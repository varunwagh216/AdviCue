from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    advisor_demo_operations_enabled: bool = os.getenv("ADVISOR_WORKSPACE_OPERATIONS_ENABLED", os.getenv("ADVISOR_DEMO_OPERATIONS_ENABLED", "false")).lower() == "true"
    advisor_demo_operator_email: str = os.getenv("ADVISOR_WORKSPACE_OPERATOR_EMAIL", os.getenv("ADVISOR_DEMO_OPERATOR_EMAIL", "advisor@advicue.local"))
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./advicue.db")
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    cookie_secure: bool = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    llama_cpp_url: str = os.getenv("LLAMA_CPP_URL", "http://127.0.0.1:8080")
    llama_cpp_model: str = os.getenv("LLAMA_CPP_MODEL", "advicue-llama-1b-q4_k_m")
    whisper_model: str = os.getenv("WHISPER_MODEL", "base")
    whisper_cpp_executable: str = os.getenv('WHISPER_CPP_EXECUTABLE', 'local_ai/whisper/whisper-cli.exe' if os.name=='nt' else 'local_ai/whisper/whisper-cli')
    whisper_cpp_model: str = os.getenv('WHISPER_CPP_MODEL', 'local_ai/models/ggml-base.bin')
    local_ffmpeg: str = os.getenv('LOCAL_FFMPEG', 'local_ai/ffmpeg/ffmpeg.exe' if os.name=='nt' else 'local_ai/ffmpeg/ffmpeg')
    max_audio_mb: int = int(os.getenv("MAX_AUDIO_MB", "12"))
    session_hours: int = int(os.getenv("SESSION_HOURS", "8"))


settings = Settings()
