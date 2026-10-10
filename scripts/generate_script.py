#!/usr/bin/env python3
"""
generate_script.py
Gera o roteiro do vídeo utilizando a OpenRouter API com fallback entre modelos.
"""

import json
import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
import requests

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


def load_config(base_dir: Path) -> tuple[dict, list, str]:
    """Carrega as configurações do projeto."""
    settings_path = base_dir / "config" / "settings.json"
    models_path = base_dir / "config" / "models.json"
    master_prompt_path = base_dir / "config" / "master_prompt.txt"

    if not settings_path.exists():
        logger.error(f"Arquivo de configuração não encontrado: {settings_path}")
        sys.exit(1)

    if not models_path.exists():
        logger.error(f"Arquivo de modelos não encontrado: {models_path}")
        sys.exit(1)

    if not master_prompt_path.exists():
        logger.error(f"Prompt mestre não encontrado: {master_prompt_path}")
        sys.exit(1)

    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    with open(models_path, "r", encoding="utf-8") as f:
        models_data = json.load(f)
        models = models_data.get("models", [])

    with open(master_prompt_path, "r", encoding="utf-8") as f:
        master_prompt = f.read().strip()

    return settings, models, master_prompt


def call_openrouter(
    api_key: str,
    model_id: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
    base_url: str,
    timeout: int
) -> str | None:
    """Faz uma chamada à OpenRouter API e retorna o conteúdo gerado."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/gerar-videos-grok",
        "X-Title": "Gerar Videos Grok Pipeline"
    }

    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    try:
        logger.info(f"Chamando modelo: {model_id}")
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout
        )

        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
            logger.info(f"Resposta recebida com sucesso do modelo {model_id}")
            return content
        else:
            logger.warning(
                f"Modelo {model_id} retornou status {response.status_code}: {response.text[:200]}"
            )
            return None

    except requests.exceptions.Timeout:
        logger.warning(f"Timeout ao chamar modelo {model_id}")
        return None
    except requests.exceptions.ConnectionError as e:
        logger.warning(f"Erro de conexão com modelo {model_id}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Erro inesperado ao chamar modelo {model_id}: {e}")
        return None


def parse_structured_response(content: str) -> dict | None:
    """
    Parseia a resposta estruturada do novo master prompt (seções de texto).
    Extrai: CONCEITO, GANCHO, PROMPT PARA GROK IMAGINE, LEGENDA, HASHTAGS.
    """
    import re

    def extract_section(text: str, section: str) -> str:
        """Extrai o conteúdo de uma seção do texto estruturado."""
        # Tenta com ### SECTION ou ** SECTION ** ou apenas SECTION
        patterns = [
            rf"###\s*{re.escape(section)}\s*\n(.*?)(?=###|\Z)",
            rf"\*\*{re.escape(section)}\*\*\s*\n(.*?)(?=\*\*|\Z)",
            rf"{re.escape(section)}\s*\n(.*?)(?=\n[A-Z#*]|\Z)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
        return ""

    conceito = extract_section(content, "CONCEITO")
    
    # Suporta o formato antigo e o novo
    gancho = extract_section(content, "NARRAÇÃO (PORTUGUÊS BRASILEIRO)") or extract_section(content, "NARRAÇÃO") or extract_section(content, "GANCHO")
    prompt_grok = extract_section(content, "PROMPT VISUAL (ENGLISH)") or extract_section(content, "PROMPT VISUAL") or extract_section(content, "PROMPT PARA GROK IMAGINE")
    
    legenda = extract_section(content, "LEGENDA PARA FACEBOOK")
    hashtags = extract_section(content, "HASHTAGS")

    # Se não achou seções estruturadas, usa o conteúdo completo como prompt
    if not prompt_grok:
        logger.warning("Seção 'PROMPT PARA GROK IMAGINE' não encontrada. Usando conteúdo completo como prompt.")
        prompt_grok = content.strip()

    if not conceito:
        conceito = "Vídeo Viral Brasil"

    return {
        "titulo": conceito,
        "prompt_visual": prompt_grok,
        "narracao": gancho,
        "legenda": legenda,
        "hashtags": hashtags,
        "conceito": conceito,
        "gancho": gancho,
    }


def validate_script(content: str, settings: dict) -> dict | None:
    """Valida e parseia o roteiro gerado."""
    script_config = settings.get("script", {})
    min_len = script_config.get("min_length_chars", 50)
    max_len = script_config.get("max_length_chars", 2000)
    validate_json = script_config.get("validate_json", True)

    if not content:
        logger.error("Conteúdo do roteiro está vazio")
        return None

    # Tenta parsear como JSON primeiro (compatibilidade com formato antigo)
    if validate_json:
        content_clean = content
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            content_clean = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            content_clean = content[start:end].strip()

        try:
            script_data = json.loads(content_clean)
            # Formato JSON antigo — valida campos
            required_fields = ["titulo", "prompt_visual", "narracao"]
            for field in required_fields:
                if field not in script_data:
                    raise ValueError(f"Campo obrigatório ausente: {field}")
            logger.info(f"Roteiro em formato JSON válido: '{script_data.get('titulo')}'")
        except (json.JSONDecodeError, ValueError):
            # Não é JSON — tenta parsear como texto estruturado (novo formato)
            logger.info("Resposta não é JSON. Tentando parsear como texto estruturado...")
            script_data = parse_structured_response(content)
            if not script_data:
                logger.error("Falha ao parsear resposta como texto estruturado.")
                return None
            logger.info(f"Roteiro parseado do texto estruturado: '{script_data.get('titulo')}'")
    else:
        script_data = parse_structured_response(content)

    # Valida tamanho do prompt visual
    prompt_visual = script_data.get("prompt_visual", "")
    if len(prompt_visual) < min_len:
        logger.error(f"Prompt visual muito curto: {len(prompt_visual)} chars (mínimo: {min_len})")
        return None

    if len(prompt_visual) > max_len:
        logger.warning(f"Prompt visual muito longo ({len(prompt_visual)} chars), truncando para {max_len}")
        script_data["prompt_visual"] = prompt_visual[:max_len]

    logger.info(f"Roteiro validado: '{script_data.get('titulo', 'Sem título')}'")
    return script_data



def save_script(script_data: dict, output_dir: Path) -> Path:
    """Salva o roteiro gerado em arquivo JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"script_{timestamp}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)

    logger.info(f"Roteiro salvo em: {output_path}")
    return output_path


def generate_script_with_fallback(
    api_key: str,
    models: list,
    master_prompt: str,
    settings: dict
) -> dict | None:
    """Tenta gerar o roteiro usando os modelos em ordem de prioridade."""
    or_config = settings.get("openrouter", {})
    base_url = or_config.get("base_url", "https://openrouter.ai/api/v1")
    timeout = or_config.get("timeout_seconds", 60)
    max_retries = or_config.get("max_retries", 3)
    retry_delay = or_config.get("retry_delay_seconds", 10)

    for model in models:
        model_id = model.get("id")
        max_tokens = model.get("max_tokens", 1024)
        temperature = model.get("temperature", 0.8)
        model_name = model.get("name", model_id)

        logger.info(f"Tentando modelo: {model_name}")

        for attempt in range(1, max_retries + 1):
            if attempt > 1:
                logger.info(f"Tentativa {attempt}/{max_retries} para {model_name}")
                time.sleep(retry_delay)

            content = call_openrouter(
                api_key=api_key,
                model_id=model_id,
                prompt=master_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                base_url=base_url,
                timeout=timeout
            )

            if content:
                script_data = validate_script(content, settings)
                if script_data:
                    script_data["_meta"] = {
                        "model_used": model_id,
                        "model_name": model_name,
                        "generated_at": datetime.now().isoformat(),
                        "attempt": attempt
                    }
                    return script_data
                else:
                    logger.warning(f"Roteiro inválido do modelo {model_name}, tentando novamente...")

        logger.warning(f"Modelo {model_name} falhou após {max_retries} tentativas. Passando para o próximo.")

    logger.error("Todos os modelos falharam. Não foi possível gerar o roteiro.")
    return None


def main():
    """Função principal."""
    base_dir = Path(__file__).parent.parent

    # Verifica API key
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        logger.error("Variável de ambiente OPENROUTER_API_KEY não encontrada.")
        logger.error("Configure esta variável como GitHub Secret.")
        sys.exit(1)

    logger.info("=== INICIANDO GERAÇÃO DE ROTEIRO ===")

    # Carrega configurações
    settings, models, master_prompt = load_config(base_dir)
    logger.info(f"Modelos disponíveis: {len(models)}")
    logger.info(f"Prompt mestre carregado ({len(master_prompt)} chars)")

    # Gera roteiro com fallback
    script_data = generate_script_with_fallback(api_key, models, master_prompt, settings)

    if not script_data:
        logger.error("Falha na geração do roteiro. Abortando pipeline.")
        sys.exit(1)

    # Salva roteiro
    output_dir = base_dir / settings.get("output", {}).get("scripts_dir", "output/scripts")
    script_path = save_script(script_data, output_dir)

    # Exporta caminho para uso em steps seguintes do GitHub Actions
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"script_path={script_path}\n")
            f.write(f"script_title={script_data.get('titulo', 'Video')}\n")
            prompt_visual = script_data.get("prompt_visual", "")
            # Escapa quebras de linha para o GITHUB_OUTPUT
            prompt_visual_escaped = prompt_visual.replace("\n", " ").replace("\r", "")
            f.write(f"prompt_visual={prompt_visual_escaped}\n")

    logger.info("=== ROTEIRO GERADO COM SUCESSO ===")
    logger.info(f"Título: {script_data.get('titulo', 'N/A')}")
    logger.info(f"Modelo usado: {script_data.get('_meta', {}).get('model_used', 'N/A')}")
    logger.info(f"Arquivo: {script_path}")

    print(f"SCRIPT_PATH={script_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
