#!/usr/bin/env python3
"""
send_facebook.py
Gera uma legenda SEO via OpenRouter com base na narração e envia o vídeo processado para uma Página do Facebook.
"""

import json
import logging
import os
import sys
import requests
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def generate_caption(narracao: str, openrouter_key: str) -> str:
    """Usa o OpenRouter para gerar uma legenda viral e otimizada para SEO."""
    if not openrouter_key:
        # Se não tiver a chave, faz um fallback
        return f"{narracao}\n\n#Receita #ReceitaFacil #CulinariaBrasileira #DicaDeCozinha #ComidaBoa"
    
    logger.info("Gerando legenda otimizada para SEO via OpenRouter...")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {openrouter_key}",
        "Content-Type": "application/json"
    }
    prompt = (
        f"Transforme o texto abaixo em uma legenda viral e engajadora para uma página de receitas no Facebook chamada 'Rainha da Shopee'. "
        f"Adicione emojis, resuma o modo de preparo de forma atrativa e inclua exatamente 5 hashtags altamente otimizadas para SEO.\n\n"
        f"Texto base: {narracao}"
    )
    
    data = {
        "model": "nvidia/nemotron-3-ultra-550b-a55b:free",  # Usando o modelo gratuito configurado no projeto
        "messages": [
            {"role": "system", "content": "Você é um Social Media e Copywriter especialista em receitas virais para o Facebook."},
            {"role": "user", "content": prompt}
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        result = response.json()
        caption = result["choices"][0]["message"]["content"].strip()
        logger.info("Legenda gerada com sucesso!")
        return caption
    except Exception as e:
        logger.error(f"Erro ao gerar legenda: {e}")
        return f"{narracao}\n\n#Receita #ReceitaFacil #CulinariaBrasileira #DicaDeCozinha #ComidaBoa"


def main():
    bot_token = os.environ.get("FACEBOOK_PAGE_TOKEN", "")
    page_id = os.environ.get("FACEBOOK_PAGE_ID", "")
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")

    if not bot_token or not page_id:
        logger.error("FACEBOOK_PAGE_TOKEN ou FACEBOOK_PAGE_ID não configurados.")
        sys.exit(1)

    processed_path_str = os.environ.get("PROCESSED_PATH", "")
    script_path_str = os.environ.get("SCRIPT_PATH", "")

    if not processed_path_str or not os.path.exists(processed_path_str):
        logger.error("PROCESSED_PATH não encontrado.")
        sys.exit(1)

    narracao = "Vídeo gerado automaticamente"
    if script_path_str and os.path.exists(script_path_str):
        with open(script_path_str, "r", encoding="utf-8") as f:
            data = json.load(f)
            narracao = data.get("narracao", narracao)

    caption = generate_caption(narracao, openrouter_key)

    logger.info("=== INICIANDO ENVIO PARA FACEBOOK ===")
    
    api_url = f"https://graph.facebook.com/v19.0/{page_id}/videos"
    
    try:
        with open(processed_path_str, "rb") as video_file:
            data = {
                "access_token": bot_token,
                "description": caption
            }
            files = {
                "source": (os.path.basename(processed_path_str), video_file, "video/mp4")
            }
            logger.info("Enviando vídeo (pode demorar alguns minutos)...")
            response = requests.post(api_url, data=data, files=files, timeout=600)
            
            if response.status_code == 200:
                result = response.json()
                video_id = result.get("id")
                logger.info(f"Vídeo publicado com sucesso! ID: {video_id}")
            else:
                logger.error(f"Falha ao enviar. Status: {response.status_code}, Erro: {response.text}")
                sys.exit(1)
    except Exception as e:
        logger.error(f"Erro inesperado durante o upload: {e}")
        sys.exit(1)

    logger.info("=== ENVIO CONCLUÍDO ===")
    return 0

if __name__ == "__main__":
    sys.exit(main())
