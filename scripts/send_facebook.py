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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


import re

def generate_caption(titulo: str, narracao: str, openrouter_key: str) -> str:
    """Usa o OpenRouter para gerar uma legenda viral e otimizada para SEO focada na receita atual."""
    tag_limpa = "".join(c for c in titulo.lower() if c.isalnum())
    if not tag_limpa:
        tag_limpa = "receitadodia"

    fallback_caption = (
        f"✨ {titulo.upper()} ✨\n\n"
        f"{narracao}\n\n"
        f"Gostou dessa receita prática e deliciosa? Salva para não perder e já compartilha com a família! ❤️\n\n"
        f"#{tag_limpa} #receitafacil #receitacaseira #culinariabrasileira #comidaboa"
    )

    if not openrouter_key:
        logger.warning("OPENROUTER_API_KEY não encontrada. Usando legenda padrão formatada.")
        return fallback_caption
    
    logger.info(f"Gerando legenda SEO exclusiva para '{titulo}' via OpenRouter...")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {openrouter_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/gerar-videos-grok",
        "X-Title": "Facebook Caption Generator"
    }
    
    prompt = (
        f"Você é o Social Media e Copywriter oficial da página do Facebook 'Rainha da Shopee' (público brasileiro, famílias e amantes de culinária caseira).\n\n"
        f"Crie uma legenda VIRAL, irresistível e completa para a postagem deste vídeo de receita:\n"
        f"Nome da receita: {titulo}\n"
        f"Modo de preparo / narração: {narracao}\n\n"
        f"REGRAS OBRIGATÓRIAS:\n"
        f"1. Comece com um título chamativo e apetitoso com emojis destacando a receita ({titulo}).\n"
        f"2. Descreva os ingredientes e o passo a passo de forma simples, convidativa e acolhedora.\n"
        f"3. Adicione uma chamada para ação envolvente (ex: 'Salva pra fazer no fim de semana e comenta o que achou!').\n"
        f"4. No final, adicione OBRIGATORIAMENTE exatamente 5 hashtags relacionadas com essa receita específica, TODAS EM LETRAS MINÚSCULAS (exemplo: #{tag_limpa} #receitafacil #receitas #culinaria #comidaboa).\n"
        f"5. NUNCA use letras maiúsculas nas hashtags. Não repita legendas genéricas."
    )
    
    data = {
        "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "temperature": 0.85,
        "messages": [
            {
                "role": "system",
                "content": "Você é especialista em copywriting gastronômico viral para o Facebook. Você SEMPRE cria legendas únicas, personalizadas para a receita exata fornecida e com todas as hashtags em minúsculas."
            },
            {"role": "user", "content": prompt}
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=45)
        response.raise_for_status()
        result = response.json()
        caption = result["choices"][0]["message"]["content"].strip()

        # Garante que as hashtags estejam rigorosamente em minúsculas
        def lowercase_hashtags(text: str) -> str:
            return re.sub(r'#([a-zA-Z0-9_]+)', lambda m: f"#{m.group(1).lower()}", text)

        caption = lowercase_hashtags(caption)
        logger.info("Legenda gerada com sucesso pela IA!")
        return caption
    except Exception as e:
        logger.error(f"Erro ao gerar legenda via OpenRouter ({e}). Usando fallback personalizado.")
        return fallback_caption


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

    titulo = "Receita Especial"
    narracao = "Vídeo gerado automaticamente"

    if script_path_str and os.path.exists(script_path_str):
        try:
            with open(script_path_str, "r", encoding="utf-8") as f:
                data = json.load(f)
                titulo = data.get("titulo", titulo)
                narracao = data.get("narracao", narracao)
                logger.info(f"Roteiro carregado de '{script_path_str}': {titulo}")
        except Exception as e:
            logger.warning(f"Falha ao ler roteiro JSON: {e}")

    caption = generate_caption(titulo, narracao, openrouter_key)

    logger.info("==================================================")
    logger.info(f"📢 PUBLICAÇÃO FACEBOOK - RECEITA: {titulo}")
    logger.info("--- LEGENDA A SER ENVIADA ---")
    logger.info(caption)
    logger.info("==================================================")
    
    api_url = f"https://graph.facebook.com/v19.0/{page_id}/videos"
    
    try:
        with open(processed_path_str, "rb") as video_file:
            data = {
                "access_token": bot_token,
                "description": caption,
                "title": titulo
            }
            files = {
                "source": (os.path.basename(processed_path_str), video_file, "video/mp4")
            }
            logger.info("Enviando vídeo para o Facebook (pode demorar alguns minutos)...")
            response = requests.post(api_url, data=data, files=files, timeout=600)
            
            if response.status_code == 200:
                result = response.json()
                video_id = result.get("id")
                logger.info(f"✅ Vídeo publicado com sucesso no Facebook! Video ID: {video_id}")
            else:
                logger.error(f"❌ Falha ao enviar para o Facebook. Status: {response.status_code}, Erro: {response.text}")
                sys.exit(1)
    except Exception as e:
        logger.error(f"Erro inesperado durante o upload: {e}")
        sys.exit(1)

    logger.info("=== ENVIO FACEBOOK CONCLUÍDO COM SUCESSO ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
