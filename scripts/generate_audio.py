#!/usr/bin/env python3
"""
generate_audio.py
Gera a narração em áudio para o vídeo utilizando a Fish Audio API (plano gratuito s2.1-pro-free).
Possui fallback automático para o Edge-TTS caso a API do Fish Audio esteja indisponível.
"""

import json
import os
import re
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def load_config(base_dir: Path) -> dict:
    """Carrega as configurações."""
    settings_path = base_dir / "config" / "settings.json"
    if not settings_path.exists():
        logger.error(f"Arquivo de configurações não encontrado: {settings_path}")
        sys.exit(1)
    with open(settings_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_script(script_path: str) -> dict:
    """Carrega o roteiro JSON gerado pelo step anterior."""
    path = Path(script_path)
    if not path.exists():
        logger.error(f"Arquivo de roteiro não encontrado: {script_path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_audio_fish(
    text: str,
    output_path: Path,
    api_key: str,
    voice_id: str,
    model: str = "s2.1-pro-free"
) -> bool:
    """
    Sintetiza áudio via Fish Audio API usando o modelo gratuito s2.1-pro-free.
    """
    url = "https://api.fish.audio/v1/tts"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "model": model
    }
    payload = {
        "text": text,
        "reference_id": voice_id,
        "format": "mp3",
        "mp3_bitrate": 192,
        "normalize": True,
        "latency": "normal"
    }

    logger.info(f"Enviando texto para Fish Audio API (voz: {voice_id}, modelo: {model})...")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code == 200 and len(response.content) > 1000:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(response.content)
            logger.info(f"✅ Áudio gerado com sucesso via Fish Audio: {output_path.name} ({len(response.content)/1024:.1f} KB)")
            return True
        else:
            logger.warning(f"Fish Audio retornou status {response.status_code}: {response.text[:250]}")
            return False
    except Exception as e:
        logger.warning(f"Erro na requisição para Fish Audio: {e}")
        return False


def generate_audio_edge(text: str, output_path: Path, voice: str = "pt-BR-FranciscaNeural") -> bool:
    """
    Fallback: sintetiza áudio usando edge-tts caso o Fish Audio falhe.
    """
    try:
        import asyncio
        import edge_tts

        logger.info(f"Ativando fallback Edge-TTS (voz: {voice})...")

        async def _run():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(output_path))

        asyncio.run(_run())

        if output_path.exists() and output_path.stat().st_size > 1000:
            logger.info(f"✅ Áudio gerado com sucesso via Edge-TTS (fallback): {output_path.name}")
            return True
        return False
    except ImportError:
        logger.warning("edge-tts não instalado, tentando chamada via CLI...")
        try:
            import subprocess
            cmd = ["edge-tts", "--voice", voice, "--text", text, "--write-media", str(output_path)]
            res = subprocess.run(cmd, capture_output=True, timeout=30)
            if res.returncode == 0 and output_path.exists():
                return True
        except Exception:
            pass
        return False
    except Exception as e:
        logger.error(f"Erro ao gerar áudio com Edge-TTS: {e}")
        return False


def main():
    """Função principal."""
    base_dir = Path(__file__).parent.parent
    settings = load_config(base_dir)

    script_path = os.environ.get("SCRIPT_PATH", "").strip()
    narracao_env = os.environ.get("NARRACAO", "").strip()

    if not script_path and not narracao_env:
        logger.error("SCRIPT_PATH ou NARRACAO não definidos.")
        sys.exit(1)

    narracao = narracao_env
    titulo = "audio"
    if script_path:
        script_data = load_script(script_path)
        narracao = script_data.get("narracao", narracao_env)
        titulo = script_data.get("titulo", "audio")

    # Limpa resíduos de formatação
    narracao = re.sub(r'[\r\n\s]*(?:---+|\*\*\*+|===+|___+)[\r\n\s]*$', '', narracao).strip().strip('"\'')

    if not narracao:
        logger.error("Texto de narração vazio. Não é possível gerar áudio.")
        sys.exit(1)

    logger.info("=== INICIANDO GERAÇÃO DE ÁUDIO ===")
    logger.info(f"Título: {titulo}")
    logger.info(f"Narração ({len(narracao)} caracteres): {narracao[:120]}...")

    # Configurações de TTS
    tts_config = settings.get("tts", {})
    api_key = os.environ.get("FISH_API_KEY", "").strip()
    voice_id = os.environ.get("FISH_VOICE_ID", "").strip() or tts_config.get("voice_id", "da20590a048f483986bf9986e6a87694")
    model = tts_config.get("model", "s2.1-pro-free")
    fallback_voice = tts_config.get("fallback_voice", "pt-BR-FranciscaNeural")

    # Diretório de saída
    output_dir = base_dir / settings.get("output", {}).get("audio_dir", "output/audio")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_titulo = "".join(c for c in titulo if c.isalnum() or c in " _-").strip()[:30]
    audio_filename = f"audio_{safe_titulo}_{timestamp}.mp3"
    audio_output_path = output_dir / audio_filename

    success = False
    provider_used = "fish_audio"

    # 1. Tenta Fish Audio se tiver chave
    if api_key and voice_id:
        success = generate_audio_fish(
            text=narracao,
            output_path=audio_output_path,
            api_key=api_key,
            voice_id=voice_id,
            model=model
        )

    # 2. Se falhar, aciona Edge-TTS como fallback gratuito
    if not success:
        logger.warning("Fish Audio indisponível ou falhou. Acionando fallback Edge-TTS...")
        success = generate_audio_edge(
            text=narracao,
            output_path=audio_output_path,
            voice=fallback_voice
        )
        provider_used = "edge_tts"

    if not success or not audio_output_path.exists():
        logger.error("Falha ao gerar áudio por todos os métodos disponíveis.")
        sys.exit(1)

    # Exporta caminho para steps seguintes no GitHub Actions
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"audio_path={audio_output_path}\n")
            f.write(f"audio_filename={audio_filename}\n")
            f.write(f"audio_provider={provider_used}\n")

    logger.info("=== ÁUDIO GERADO COM SUCESSO ===")
    logger.info(f"Arquivo: {audio_output_path} (Provedor: {provider_used})")
    print(f"AUDIO_PATH={audio_output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
