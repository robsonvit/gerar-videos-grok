#!/usr/bin/env python3
"""
process_video.py
Processa o vídeo gerado usando FFmpeg:
- Normalização de volume (loudnorm)
- Conversão para H.264 + AAC
- Garantia de formato vertical 9:16
- Otimização para redes sociais
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def load_config(base_dir: Path) -> dict:
    """Carrega as configurações."""
    settings_path = base_dir / "config" / "settings.json"
    with open(settings_path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_ffmpeg() -> bool:
    """Verifica se o FFmpeg está instalado e disponível."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            version_line = result.stdout.split("\n")[0]
            logger.info(f"FFmpeg encontrado: {version_line}")
            return True
        return False
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.error("FFmpeg não encontrado. Instale o FFmpeg e tente novamente.")
        return False


def get_video_info(video_path: Path) -> dict | None:
    """Obtém informações do vídeo usando ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                "-show_format",
                str(video_path)
            ],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            info = json.loads(result.stdout)
            return info
        else:
            logger.warning(f"ffprobe retornou erro: {result.stderr[:200]}")
            return None

    except Exception as e:
        logger.warning(f"Erro ao obter info do vídeo: {e}")
        return None


def validate_video_duration(video_path: Path, expected_duration: float, tolerance: float = 5.0) -> bool:
    """Valida se a duração do vídeo está dentro da tolerância esperada."""
    info = get_video_info(video_path)
    if not info:
        logger.warning("Não foi possível validar a duração (sem info do ffprobe)")
        return True  # Continua mesmo sem validação

    duration = float(info.get("format", {}).get("duration", 0))
    if duration == 0:
        # Tenta obter do stream de vídeo
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "video":
                duration = float(stream.get("duration", 0))
                break

    logger.info(f"Duração do vídeo: {duration:.1f}s (esperado: ~{expected_duration}s)")

    if duration < 1:
        logger.error(f"Duração inválida: {duration}s")
        return False

    return True


def check_audio_stream(video_path: Path) -> bool:
    """Verifica se o vídeo possui stream de áudio."""
    info = get_video_info(video_path)
    if not info:
        return True  # Assume que tem áudio se não conseguir verificar

    has_audio = any(
        stream.get("codec_type") == "audio"
        for stream in info.get("streams", [])
    )

    if has_audio:
        logger.info("Stream de áudio detectado no vídeo")
    else:
        logger.warning("Vídeo sem stream de áudio detectado")

    return has_audio


def process_video(
    input_path: Path,
    output_path: Path,
    settings: dict
) -> bool:
    """
    Processa o vídeo com FFmpeg aplicando:
    - Normalização de loudness (EBU R128)
    - Conversão para H.264 + AAC
    - Padronização de resolução vertical
    - Otimização de bitrate
    """
    video_config = settings.get("video", {})
    audio_config = settings.get("audio", {})

    codec_video = video_config.get("codec_video", "libx264")
    codec_audio = video_config.get("codec_audio", "aac")
    audio_bitrate = video_config.get("audio_bitrate", "128k")
    video_bitrate = video_config.get("video_bitrate", "2000k")
    fps = video_config.get("fps", 30)

    target_loudness = audio_config.get("target_loudness_lufs", -16)
    true_peak = audio_config.get("true_peak_dbtp", -1.5)
    lra = audio_config.get("loudness_range_lra", 11)
    normalize = audio_config.get("normalize", True)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Verifica se tem áudio para normalizar
    has_audio = check_audio_stream(input_path)

    # Monta filtros de vídeo
    # scale2ref garante que o vídeo fique em formato vertical 9:16
    video_filters = [
        "scale=720:1280:force_original_aspect_ratio=decrease",
        "pad=720:1280:(ow-iw)/2:(oh-ih)/2:black",
        f"fps={fps}"
    ]
    vf_string = ",".join(video_filters)

    # Monta filtros de áudio
    if has_audio and normalize:
        af_string = (
            f"loudnorm=I={target_loudness}:TP={true_peak}:LRA={lra}:"
            f"print_format=summary"
        )
    else:
        af_string = None

    # Constrói o comando FFmpeg
    cmd = [
        "ffmpeg",
        "-y",  # Sobrescreve sem perguntar
        "-i", str(input_path),
        "-vf", vf_string,
        "-c:v", codec_video,
        "-preset", "medium",
        "-crf", "23",
        "-b:v", video_bitrate,
        "-maxrate", video_bitrate,
        "-bufsize", "4000k",
        "-pix_fmt", "yuv420p",  # Compatibilidade máxima
        "-movflags", "+faststart",  # Streaming otimizado
    ]

    if has_audio and af_string:
        cmd.extend(["-af", af_string])
        cmd.extend(["-c:a", codec_audio])
        cmd.extend(["-b:a", audio_bitrate])
        cmd.extend(["-ar", "44100"])  # Sample rate padrão
    elif has_audio:
        cmd.extend(["-c:a", codec_audio])
        cmd.extend(["-b:a", audio_bitrate])
    else:
        cmd.extend(["-an"])  # Remove áudio se não existir

    # Adiciona configurações de compatibilidade
    cmd.extend([
        "-profile:v", "high",
        "-level", "4.0",
        str(output_path)
    ])

    logger.info(f"Executando FFmpeg: {' '.join(cmd[:8])}...")
    logger.info(f"Input: {input_path}")
    logger.info(f"Output: {output_path}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode == 0:
            logger.info("FFmpeg concluído com sucesso")
            if result.stderr:
                # Log das últimas linhas do FFmpeg (útil para ver loudnorm stats)
                stderr_lines = result.stderr.strip().split("\n")
                for line in stderr_lines[-10:]:
                    if line.strip():
                        logger.debug(f"FFmpeg: {line}")
            return True
        else:
            logger.error(f"FFmpeg falhou com código {result.returncode}")
            logger.error(f"STDERR: {result.stderr[-500:]}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("FFmpeg excedeu timeout de 300 segundos")
        return False
    except FileNotFoundError:
        logger.error("FFmpeg não encontrado no PATH")
        return False
    except Exception as e:
        logger.error(f"Erro ao executar FFmpeg: {e}")
        return False


def validate_output(output_path: Path, settings: dict) -> bool:
    """Valida o arquivo de saída processado."""
    video_config = settings.get("video", {})
    max_size_mb = video_config.get("max_file_size_mb", 50)
    expected_duration = video_config.get("target_duration_seconds", 15)

    if not output_path.exists():
        logger.error(f"Arquivo de saída não encontrado: {output_path}")
        return False

    # Verifica tamanho
    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(f"Tamanho do arquivo processado: {size_mb:.2f} MB")

    if size_mb > max_size_mb:
        logger.warning(f"Arquivo grande: {size_mb:.2f} MB (limite: {max_size_mb} MB)")
        logger.warning("Pode haver problemas no envio pelo Telegram")

    if size_mb < 0.1:
        logger.error(f"Arquivo muito pequeno ({size_mb:.2f} MB), provável corrupção")
        return False

    # Valida duração
    validate_video_duration(output_path, expected_duration)

    logger.info(f"Validação concluída: {output_path.name}")
    return True


def main():
    """Função principal."""
    base_dir = Path(__file__).parent.parent

    # Parâmetros via variáveis de ambiente
    video_path_str = os.environ.get("VIDEO_PATH", "")

    if not video_path_str:
        logger.error("Variável VIDEO_PATH não definida.")
        sys.exit(1)

    input_paths = [Path(p.strip()) for p in video_path_str.split(",") if p.strip()]
    
    if not input_paths:
        logger.error("Nenhum arquivo de entrada fornecido.")
        sys.exit(1)
        
    for p in input_paths:
        if not p.exists():
            logger.error(f"Arquivo de entrada não encontrado: {p}")
            sys.exit(1)

    # Se há mais de um vídeo, concatena usando ffmpeg concat demuxer
    if len(input_paths) > 1:
        logger.info(f"Concatenando {len(input_paths)} vídeos...")
        concat_file = input_paths[0].parent / "concat.txt"
        with open(concat_file, "w", encoding="utf-8") as f:
            for p in input_paths:
                f.write(f"file '{p.absolute().as_posix()}'\n")
        
        concat_output = input_paths[0].parent / f"concatenated_{input_paths[0].name}"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(concat_output)],
            check=True
        )
        logger.info(f"Vídeos concatenados em: {concat_output}")
        input_path = concat_output
    else:
        input_path = input_paths[0]

    if not check_ffmpeg():
        sys.exit(1)

    settings = load_config(base_dir)

    # Define caminho de saída
    output_config = settings.get("output", {})
    processed_dir = base_dir / output_config.get("processed_dir", "output/processed")
    processed_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"processed_{timestamp}.mp4"
    output_path = processed_dir / output_filename

    logger.info("=== INICIANDO PROCESSAMENTO DE VÍDEO ===")
    logger.info(f"Input: {input_path}")
    logger.info(f"Output: {output_path}")

    # Valida duração do input antes de processar
    expected_duration = settings.get("video", {}).get("target_duration_seconds", 15)
    validate_video_duration(input_path, expected_duration)

    # Processa o vídeo
    success = process_video(input_path, output_path, settings)

    if not success:
        logger.error("Falha no processamento do vídeo. Abortando pipeline.")
        sys.exit(1)

    # Valida o output
    if not validate_output(output_path, settings):
        logger.error("Arquivo processado inválido. Abortando pipeline.")
        sys.exit(1)

    # Exporta para o próximo step
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"processed_path={output_path}\n")
            f.write(f"processed_filename={output_filename}\n")

    logger.info("=== PROCESSAMENTO CONCLUÍDO COM SUCESSO ===")
    logger.info(f"Arquivo final: {output_path}")
    print(f"PROCESSED_PATH={output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
