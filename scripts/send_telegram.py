#!/usr/bin/env python3
"""
send_telegram.py
Envia o vídeo processado para um bot do Telegram usando a Bot API.
"""

import json
import logging
import os
import sys
import html
from datetime import datetime
from pathlib import Path

import requests

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


def load_script_info(script_path: str) -> dict:
    """Carrega informações do roteiro para uso na legenda."""
    if not script_path:
        return {}
    path = Path(script_path)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def build_caption(script_data: dict, video_filename: str, settings: dict) -> str:
    """Monta a legenda do vídeo para envio no Telegram."""
    tg_config = settings.get("telegram", {})
    send_caption = tg_config.get("send_caption", True)

    if not send_caption:
        return ""

    titulo = html.escape(script_data.get("titulo", "Vídeo Gerado"))
    narracao = html.escape(script_data.get("narracao", ""))
    
    if len(narracao) > 800:
        narracao = narracao[:800] + "..."
        
    estilo = html.escape(script_data.get("estilo", ""))
    model_used = html.escape(script_data.get("_meta", {}).get("model_name", "OpenRouter"))
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M")

    caption_lines = [
        f"🎬 <b>{titulo}</b>",
    ]

    if narracao:
        caption_lines.append(f"\n📝 <i>{narracao}</i>")

    if estilo:
        caption_lines.append(f"\n🎨 Estilo: {estilo}")

    caption_lines.extend([
        f"\n🤖 Modelo: {model_used}",
        f"📅 {timestamp}",
        f"\n#videogerado #ia #shorts"
    ])

    return "\n".join(caption_lines)


def send_video_to_telegram(
    bot_token: str,
    chat_id: str,
    video_path: Path,
    caption: str,
    settings: dict,
    max_retries: int = 3
) -> bool:
    """Envia o vídeo para o Telegram usando a Bot API."""
    tg_config = settings.get("telegram", {})
    parse_mode = tg_config.get("parse_mode", "HTML")
    disable_notification = tg_config.get("disable_notification", False)

    api_url = f"https://api.telegram.org/bot{bot_token}/sendVideo"

    file_size_mb = video_path.stat().st_size / (1024 * 1024)
    logger.info(f"Enviando vídeo para Telegram: {video_path.name} ({file_size_mb:.2f} MB)")

    # Telegram Bot API tem limite de 50MB para sendVideo
    if file_size_mb > 50:
        logger.error(f"Arquivo muito grande para envio pelo Telegram ({file_size_mb:.2f} MB > 50 MB)")
        logger.error("Reduza o bitrate nas configurações ou use a API de upload em partes")
        return False

    for attempt in range(1, max_retries + 1):
        logger.info(f"Tentativa {attempt}/{max_retries} de envio para Telegram...")

        try:
            with open(video_path, "rb") as video_file:
                files = {"video": (video_path.name, video_file, "video/mp4")}
                data = {
                    "chat_id": chat_id,
                    "disable_notification": str(disable_notification).lower(),
                    "supports_streaming": "true",
                    "width": "720",
                    "height": "1280"
                }

                if caption:
                    data["caption"] = caption[:1024] if not parse_mode else caption # Se for HTML, o slice deve ser evitado ou feito antes.
                    data["parse_mode"] = parse_mode

                response = requests.post(
                    api_url,
                    files=files,
                    data=data,
                    timeout=300  # Upload pode demorar
                )

            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    message_id = result.get("result", {}).get("message_id", "N/A")
                    logger.info(f"Vídeo enviado com sucesso! Message ID: {message_id}")
                    return True
                else:
                    logger.error(f"API Telegram retornou erro: {result.get('description', 'Erro desconhecido')}")

            elif response.status_code == 413:
                logger.error("Arquivo muito grande para a API do Telegram (413 Request Entity Too Large)")
                return False  # Não adianta tentar novamente

            elif response.status_code == 429:
                retry_after = response.json().get("parameters", {}).get("retry_after", 60)
                logger.warning(f"Rate limit atingido. Aguardando {retry_after}s...")
                import time
                time.sleep(retry_after)

            else:
                logger.warning(f"Status HTTP {response.status_code}: {response.text[:200]}")

        except requests.exceptions.Timeout:
            logger.warning(f"Timeout no envio (tentativa {attempt})")
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Erro de conexão (tentativa {attempt}): {e}")
        except Exception as e:
            logger.error(f"Erro inesperado (tentativa {attempt}): {e}")

        if attempt < max_retries:
            import time
            wait = 30 * attempt
            logger.info(f"Aguardando {wait}s antes da próxima tentativa...")
            time.sleep(wait)

    logger.error(f"Todas as {max_retries} tentativas de envio falharam")
    return False


def send_error_notification(bot_token: str, chat_id: str, error_message: str):
    """Envia notificação de erro para o Telegram."""
    try:
        api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        message = (
            f"⚠️ <b>Pipeline de Vídeo - ERRO</b>\n\n"
            f"❌ {error_message}\n\n"
            f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )
        requests.post(
            api_url,
            data={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=30
        )
        logger.info("Notificação de erro enviada para o Telegram")
    except Exception as e:
        logger.warning(f"Não foi possível enviar notificação de erro: {e}")


def main():
    """Função principal."""
    base_dir = Path(__file__).parent.parent

    # Credenciais via GitHub Secrets (variáveis de ambiente)
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN não configurado como Secret/variável de ambiente")
        sys.exit(1)

    if not chat_id:
        logger.error("TELEGRAM_CHAT_ID não configurado como Secret/variável de ambiente")
        sys.exit(1)

    # Parâmetros do step anterior
    processed_path_str = os.environ.get("PROCESSED_PATH", "")
    script_path = os.environ.get("SCRIPT_PATH", "")

    if not processed_path_str:
        error_msg = "PROCESSED_PATH não definido. Etapa de processamento falhou?"
        logger.error(error_msg)
        send_error_notification(bot_token, chat_id, error_msg)
        sys.exit(1)

    processed_path = Path(processed_path_str)
    if not processed_path.exists():
        error_msg = f"Arquivo processado não encontrado: {processed_path_str}"
        logger.error(error_msg)
        send_error_notification(bot_token, chat_id, error_msg)
        sys.exit(1)

    settings = load_config(base_dir)
    script_data = load_script_info(script_path)

    caption = build_caption(script_data, processed_path.name, settings)

    logger.info("=== INICIANDO ENVIO PARA TELEGRAM ===")

    success = send_video_to_telegram(
        bot_token=bot_token,
        chat_id=chat_id,
        video_path=processed_path,
        caption=caption,
        settings=settings
    )

    if not success:
        error_msg = f"Falha no envio do vídeo para o Telegram: {processed_path.name}"
        logger.error(error_msg)
        send_error_notification(bot_token, chat_id, error_msg)
        sys.exit(1)

    logger.info("=== ENVIO CONCLUÍDO COM SUCESSO ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
