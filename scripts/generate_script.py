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

# Configuração de encoding para suportar caracteres especiais e emojis em qualquer OS
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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
) -> tuple[str | None, bool]:
    """
    Faz uma chamada à OpenRouter API e retorna (conteúdo, deve_tentar_novamente).
    Se o erro for não-recuperável (400, 401, 403, 404), deve_tentar_novamente=False.
    """
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
            choices = data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content") or msg.get("reasoning") or msg.get("text") or ""
                if isinstance(content, str) and content.strip():
                    logger.info(f"Resposta recebida com sucesso do modelo {model_id}")
                    return content.strip(), False
            logger.warning(f"Modelo {model_id} retornou 200 mas sem conteúdo de texto válido: {str(data)[:200]}")
            return None, True

        elif response.status_code in (400, 401, 403, 404):
            logger.warning(
                f"Modelo {model_id} retornou erro permanente ({response.status_code}): {response.text[:200]}"
            )
            return None, False

        else:
            logger.warning(
                f"Modelo {model_id} retornou status transitório {response.status_code}: {response.text[:200]}"
            )
            return None, True

    except requests.exceptions.Timeout:
        logger.warning(f"Timeout ({timeout}s) ao chamar modelo {model_id}")
        return None, True
    except requests.exceptions.ConnectionError as e:
        logger.warning(f"Erro de conexão com modelo {model_id}: {e}")
        return None, True
    except Exception as e:
        logger.warning(f"Erro inesperado ao chamar modelo {model_id}: {e}")
        return None, True


def parse_structured_response(content: str, tema_sugerido: str = "") -> dict | None:
    """
    Parseia a resposta estruturada do master prompt.
    Extrai blocos de PROMPT VISUAL (ENGLISH) e NARRAÇÃO (PORTUGUÊS BRASILEIRO).
    Se houver múltiplos blocos, seleciona um bloco exclusivo com narração limpa.
    """
    import re
    import random

    # Procura por blocos completos: PROMPT VISUAL seguido de NARRAÇÃO
    blocos = []
    
    # Divide por blocos de PROMPT VISUAL
    partes = re.split(r'(?i)PROMPT\s+VISUAL(?:\s*\([^\)]*\))?\s*:\s*', content)
    for p in partes:
        if not p.strip():
            continue
        # Dentro de cada parte, procura pela NARRAÇÃO
        match_narr = re.split(r'(?i)NARRAÇÃO(?:\s*\([^\)]*\))?\s*:\s*', p, maxsplit=1)
        if len(match_narr) == 2:
            prompt_vis = match_narr[0].strip()
            # A narração vai até o próximo delimitador de bloco ou fim
            narr_text = match_narr[1].strip()
            # Limpa se houver início de outro bloco ou instrução
            narr_text = re.split(r'(?i)(?:\n\s*PROMPT\s+VISUAL|\n\s*###|\n\s*\*\*PROMPT|\Z)', narr_text)[0].strip()
            # Remove delimitadores Markdown (---, ***, ===, etc.) e aspas residuais
            narr_text = re.sub(r'[\r\n\s]*(?:---+|\*\*\*+|===+|___+)[\r\n\s]*$', '', narr_text).strip()
            narr_text = re.sub(r'^[\r\n\s]*(?:---+|\*\*\*+|===+|___+)[\r\n\s]*', '', narr_text).strip().strip('"\'')
            prompt_vis = re.sub(r'[\r\n\s]*(?:---+|\*\*\*+|===+|___+)[\r\n\s]*$', '', prompt_vis).strip().strip('"\'')
            if prompt_vis and narr_text:
                blocos.append((prompt_vis, narr_text))

    if blocos:
        # Escolhe aleatoriamente um dos blocos gerados para garantir variedade máxima
        prompt_grok, gancho = random.choice(blocos)
    else:
        # Fallback genérico caso o formato venha ligeiramente diferente
        m_vis = re.search(r'(?i)PROMPT\s+VISUAL[^\n:]*:\s*(.*?)(?=\n\s*NARRAÇÃO|\Z)', content, re.DOTALL)
        prompt_grok = m_vis.group(1).strip() if m_vis else content.strip()
        
        m_narr = re.search(r'(?i)NARRAÇÃO[^\n:]*:\s*(.*?)(?=\n\s*PROMPT|\Z)', content, re.DOTALL)
        gancho = m_narr.group(1).strip() if m_narr else "Vídeo gerado automaticamente"

        # Limpa delimitadores residuais de markdown
        prompt_grok = re.sub(r'[\r\n\s]*(?:---+|\*\*\*+|===+|___+)[\r\n\s]*$', '', prompt_grok).strip().strip('"\'')
        gancho = re.sub(r'[\r\n\s]*(?:---+|\*\*\*+|===+|___+)[\r\n\s]*$', '', gancho).strip().strip('"\'')

    # Tenta extrair o nome da receita da narração
    # Padrão: 'vai fazer um(a) [delicioso(a)] [nome da receita], rápido...'
    titulo = ""
    match_titulo = re.search(r'vai\s+fazer\s+um[a]?\s+(?:delicios[oa]\s+)?([^,?.!]+)', gancho, re.IGNORECASE)
    if match_titulo:
        titulo = match_titulo.group(1).strip().title()
    elif tema_sugerido:
        titulo = tema_sugerido.title()
    else:
        titulo = "Receita Deliciosa"

    logger.info(f"Receita identificada: '{titulo}'")
    logger.info(f"Tamanho do prompt visual: {len(prompt_grok)} chars")
    logger.info(f"Narração extraída ({len(gancho)} chars): {gancho[:120]}...")

    return {
        "titulo": titulo,
        "prompt_visual": prompt_grok,
        "narracao": gancho,
        "legenda": "",
        "hashtags": "",
        "conceito": titulo,
        "gancho": gancho,
    }


RECEITAS_VARIADAS = [
    "Bolo de Cenoura com Cobertura de Chocolate Vulcão",
    "Pudim de Leite Condensado com Calda Dourada",
    "Torta Cremosa de Frango de Liquidificador",
    "Pão de Queijo Mineiro Super Recheado",
    "Mousse Aerada de Maracujá com Polpa Fresca",
    "Bolo de Milho Cremoso Caipira",
    "Brigadeiro Gourmet Macio com Granulado de Chocolate",
    "Escondidinho de Carne Seca com Purê de Mandioca",
    "Pastel de Feira Crocante com Recheio Generoso",
    "Pavê Tradicional de Chocolate com Creme de Baunilha",
    "Empadão Especial de Frango com Requeijão",
    "Bolo de Chocolate Fofinho com Calda Quente",
    "Quindim Brilhante e Amarelinho de Padaria",
    "Torta de Limão Fácil com Merengue Tostado",
    "Coxinha de Frango com Massa de Batata e Catupiry",
    "Rocambole de Doce de Leite Macio",
    "Panqueca de Carne Moída com Molho Vermelho e Queijo",
    "Cocada Cremosa de Colher",
    "Sonho Recheado com Creme de Confeiteiro",
    "Bolo de Fubá Cremoso com Queijo",
    "Mousse de Limão Rápida com Raspas",
    "Bolo de Laranja Molhadinho e Fofinho",
    "Enroladinho de Salsicha e Queijo Assado",
    "Torta Holandesa com Creme de Baunilha e Chocolate",
    "Feijão Tropeiro Mineiro Completo",
]


def validate_script(content: str, settings: dict, tema_sugerido: str = "") -> dict | None:
    """Valida e parseia o roteiro gerado."""
    script_config = settings.get("script", {})
    min_len = script_config.get("min_length_chars", 50)
    max_len = script_config.get("max_length_chars", 2500)
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
            required_fields = ["titulo", "prompt_visual", "narracao"]
            for field in required_fields:
                if field not in script_data:
                    raise ValueError(f"Campo obrigatório ausente: {field}")
            logger.info(f"Roteiro em formato JSON válido: '{script_data.get('titulo')}'")
        except (json.JSONDecodeError, ValueError):
            logger.info("Tentando parsear como texto estruturado de blocos...")
            script_data = parse_structured_response(content, tema_sugerido)
            if not script_data:
                logger.error("Falha ao parsear resposta como texto estruturado.")
                return None
    else:
        script_data = parse_structured_response(content, tema_sugerido)

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


def generate_offline_recipe(tema: str) -> dict:
    """
    Gera um roteiro local de altíssima fidelidade caso todas as chamadas de API falhem.
    Garante 100% de conformidade: formato 9:16 vertical, 15 segundos no Grok,
    começo (mistura), meio (preparo), fim (servindo) e narração brasileira entre 35 e 45 palavras.
    """
    tema_clean = tema.strip().title()
    prompt_visual = (
        f"Vertical video, 9:16 aspect ratio, exactly 15 seconds long. "
        f"First-person POV cooking footage in a cozy realistic Brazilian home kitchen with warm natural morning lighting. "
        f"0-4s Beginning: natural human hands mixing fresh ingredients for {tema_clean} in a ceramic bowl with a rustic wooden spoon, appetizing close-up textures. "
        f"4-10s Middle: fast dynamic preparation of {tema_clean}, transferring into cookware and cooking to golden perfection with gentle steam rising. "
        f"10-15s End: hands delicately cutting and serving a generous, steaming slice of the finished {tema_clean} onto a vintage plate, highlighting creamy texture, mouth-watering appetizing food presentation. "
        f"No text overlays, no subtitles, no watermarks, photorealistic 4k food videography."
    )

    narracao = (
        f"Você sabia que se misturar os ingredientes certos com muito carinho, "
        f"vai fazer um delicioso {tema_clean}, rápido, prático e muito gostoso? "
        f"Em poucos minutos fica com uma textura incrível e sabor de dar água na boca!"
    )

    logger.info(f"Roteiro offline gerado para: '{tema_clean}'")
    return {
        "titulo": tema_clean,
        "prompt_visual": prompt_visual,
        "narracao": narracao,
        "legenda": "",
        "hashtags": "",
        "conceito": tema_clean,
        "gancho": narracao,
        "_meta": {
            "model_used": "offline-fallback-generator",
            "model_name": "Gerador Local Resiliente",
            "generated_at": datetime.now().isoformat(),
            "tema_sorteado": tema_clean,
        }
    }


def generate_script_with_fallback(
    api_key: str,
    models: list,
    master_prompt: str,
    settings: dict,
    custom_prompt: str = "",
    custom_titulo: str = ""
) -> dict:
    """Tenta gerar o roteiro usando os modelos em ordem de prioridade com fallback inteligente."""
    import random
    
    # Se houver custom_prompt fornecido manualmente via GitHub Actions
    if custom_prompt:
        titulo = custom_titulo or "Receita Personalizada"
        logger.info(f"Usando prompt personalizado manual: '{titulo}'")
        return {
            "titulo": titulo,
            "prompt_visual": custom_prompt,
            "narracao": "Você sabia que se misturar os ingredientes certos com muito carinho, vai fazer uma receita deliciosa, rápida, prática e muito gostosa?",
            "legenda": "",
            "hashtags": "",
            "conceito": titulo,
            "gancho": "",
            "_meta": {
                "model_used": "manual-custom-prompt",
                "model_name": "Custom Input",
                "generated_at": datetime.now().isoformat(),
            }
        }

    # Sorteia uma receita brasileira para garantir variedade total em cada execução
    tema_sorteado = custom_titulo or random.choice(RECEITAS_VARIADAS)
    logger.info(f"🎯 Tema sorteado para esta execução: '{tema_sorteado}'")

    # Injeta instrução priorizada para gerar APENAS 1 BLOCO direto e rápido
    prompt_com_tema = (
        f"{master_prompt}\n\n"
        f"==============================\n"
        f"INSTRUÇÃO PRIORITÁRIA PARA ESTA EXECUÇÃO:\n"
        f"Atenção: ignore a instrução de gerar 15 receitas. Gere EXATAMENTE 1 ÚNICO BLOCO para a seguinte receita sorteada: '{tema_sorteado}'.\n"
        f"Formato estrito da sua resposta (gere APENAS isso, sem nenhum comentário antes ou depois):\n\n"
        f"PROMPT VISUAL (ENGLISH):\n"
        f"[Prompt em inglês, 9:16 vertical video, exactly 15 seconds, POV Brazilian kitchen, beginning mixing (0-4s), middle preparing (4-10s), end serving the dish (10-15s)]\n\n"
        f"NARRAÇÃO (PORTUGUÊS BRASILEIRO):\n"
        f"Você sabia que se misturar [ingredientes e quantidades], vai fazer um(a) delicioso(a) {tema_sorteado}, rápido, prático e muito gostoso? [breve preparo e servindo no final].\n\n"
        f"REGRAS OBRIGATÓRIAS:\n"
        f"- A narração DEVE ter entre 35 e 45 palavras no total para caber perfeitamente no ritmo de 15 segundos do vídeo.\n"
        f"- Inicie a narração obrigatoriamente com 'Você sabia que se misturar...'\n"
        f"- O prompt visual DEVE ser em inglês e descrever começo misturando (0-4s), meio preparando (4-10s) e fim servindo (10-15s)."
    )

    or_config = settings.get("openrouter", {})
    base_url = or_config.get("base_url", "https://openrouter.ai/api/v1")
    timeout = or_config.get("timeout_seconds", 35)
    max_retries = or_config.get("max_retries", 2)
    retry_delay = or_config.get("retry_delay_seconds", 5)

    if api_key:
        for model in models:
            model_id = model.get("id")
            max_tokens = model.get("max_tokens", 1024)
            temperature = model.get("temperature", 0.7)
            model_name = model.get("name", model_id)

            logger.info(f"Tentando modelo: {model_name}")

            for attempt in range(1, max_retries + 1):
                if attempt > 1:
                    logger.info(f"Tentativa {attempt}/{max_retries} para {model_name}")
                    time.sleep(retry_delay)

                content, should_retry = call_openrouter(
                    api_key=api_key,
                    model_id=model_id,
                    prompt=prompt_com_tema,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    base_url=base_url,
                    timeout=timeout
                )

                if content:
                    script_data = validate_script(content, settings, tema_sorteado)
                    if script_data:
                        script_data["_meta"] = {
                            "model_used": model_id,
                            "model_name": model_name,
                            "generated_at": datetime.now().isoformat(),
                            "attempt": attempt,
                            "tema_sorteado": tema_sorteado
                        }
                        return script_data
                    else:
                        logger.warning(f"Roteiro inválido do modelo {model_name}, tentando novamente...")

                if not should_retry:
                    logger.info(f"Pulando tentativas adicionais para {model_name} devido a erro definitivo.")
                    break

            logger.warning(f"Modelo {model_name} falhou após tentativas. Passando para o próximo.")
    else:
        logger.warning("Nenhuma OPENROUTER_API_KEY fornecida.")

    logger.warning(
        f"⚠️ Não foi possível obter resposta dos modelos remotos do OpenRouter. "
        f"Ativando gerador local resiliente para a receita: '{tema_sorteado}'..."
    )
    return generate_offline_recipe(tema_sorteado)


def main():
    """Função principal."""
    base_dir = Path(__file__).parent.parent

    # Verifica variáveis de ambiente
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    custom_prompt = os.environ.get("CUSTOM_PROMPT", "").strip()
    custom_titulo = os.environ.get("CUSTOM_TITULO", "").strip()

    logger.info("=== INICIANDO GERAÇÃO DE ROTEIRO ===")

    # Carrega configurações
    settings, models, master_prompt = load_config(base_dir)
    logger.info(f"Modelos disponíveis: {len(models)}")
    logger.info(f"Prompt mestre carregado ({len(master_prompt)} chars)")

    # Gera roteiro com fallback resiliente
    script_data = generate_script_with_fallback(
        api_key=api_key,
        models=models,
        master_prompt=master_prompt,
        settings=settings,
        custom_prompt=custom_prompt,
        custom_titulo=custom_titulo
    )

    if not script_data:
        logger.error("Falha crítica na geração do roteiro. Abortando pipeline.")
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
