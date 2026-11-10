#!/usr/bin/env python3
"""
generate_video.py
Gera vídeos gastronômicos com alta fidelidade e áudio/narração em PT-BR
utilizando a API oficial do Kie.ai (modelo Grok Imagine Text-to-Video 720p 10s).
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

# Configuração de encoding para suporte a caracteres especiais em qualquer OS
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
    """Carrega as configurações gerais."""
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


def create_kie_task(
    api_key: str,
    prompt: str,
    model: str = "runway",
    aspect_ratio: str = "9:16",
    duration: int = 5,
    resolution: str = "720p",
    mode: str = "normal"
) -> str | None:
    """
    Envia a tarefa de geração para a API do Kie.ai.
    Suporta o modelo Runway (com callBackUrl e quality) e modelos Grok/Veo.
    Retorna o taskId ou None em caso de falha.
    """
    url = "https://api.kie.ai/api/v1/jobs/createTask"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    if "runway" in model.lower():
        payload = {
            "model": "runway",
            "callBackUrl": "https://api.example.com/callback",
            "input": {
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "duration": duration,
                "quality": resolution,
                "watermark": ""
            }
        }
    else:
        payload = {
            "model": model,
            "input": {
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "duration": duration,
                "resolution": resolution,
                "mode": mode
            }
        }

    logger.info(f"Submetendo tarefa ao Kie.ai (modelo: {model}, {resolution}, {duration}s, {aspect_ratio})...")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code != 200:
            logger.error(f"Kie.ai createTask retornou status {response.status_code}: {response.text}")
            return None

        data = response.json()
        code = data.get("code")
        if code != 200:
            logger.error(f"Kie.ai createTask retornou código de erro {code}: {data.get('message', 'Erro desconhecido')}")
            return None

        task_id = data.get("data", {}).get("taskId")
        if not task_id:
            logger.error(f"Kie.ai createTask não retornou taskId: {data}")
            return None

        logger.info(f"Tarefa criada com sucesso! Task ID: {task_id}")
        return task_id

    except requests.exceptions.RequestException as e:
        logger.error(f"Erro na requisição para Kie.ai createTask: {e}")
        return None


def poll_kie_task(
    api_key: str,
    task_id: str,
    timeout_seconds: int = 300,
    poll_interval: int = 5
) -> dict | None:
    """
    Monitora a execução da tarefa no Kie.ai até a conclusão ou timeout.
    Retorna um dicionário com os dados da tarefa (url, créditos consumidos, etc.) ou None.
    """
    url = f"https://api.kie.ai/api/v1/jobs/recordInfo?taskId={task_id}"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    start_time = time.time()
    logger.info(f"Aguardando processamento da tarefa {task_id} (timeout: {timeout_seconds}s)...")

    while time.time() - start_time < timeout_seconds:
        elapsed = int(time.time() - start_time)
        try:
            response = requests.get(url, headers=headers, timeout=20)
            if response.status_code == 200:
                body = response.json()
                data = body.get("data", {})
                state = data.get("state", "unknown")

                if state == "success":
                    # Extrai a URL do vídeo
                    result_urls = data.get("response", {}).get("resultUrls", [])
                    if not result_urls and "resultJson" in data:
                        try:
                            rj = json.loads(data["resultJson"])
                            result_urls = rj.get("resultUrls", [])
                        except Exception:
                            pass

                    if result_urls and len(result_urls) > 0:
                        video_url = result_urls[0]
                        credits_consumed = data.get("creditsConsumed", 45.0)
                        if credits_consumed is None:
                            credits_consumed = 45.0
                        cost_time = data.get("costTime", elapsed)
                        logger.info(f"✅ Vídeo gerado com sucesso em {elapsed}s! (Créditos consumidos: {credits_consumed})")
                        logger.info(f"URL do vídeo: {video_url}")
                        return {
                            "video_url": video_url,
                            "credits_consumed": float(credits_consumed),
                            "cost_time": cost_time
                        }
                    else:
                        logger.error(f"Estado 'success' mas nenhuma URL de vídeo encontrada: {data}")
                        return None

                elif state == "fail":
                    fail_reason = data.get("failReason", "Motivo não informado")
                    logger.error(f"❌ Falha na geração do vídeo pelo Kie.ai: {fail_reason}")
                    return None

                else:
                    logger.info(f"[{elapsed}s] Tarefa em andamento... Estado atual: '{state}'")

            else:
                logger.warning(f"[{elapsed}s] recordInfo retornou status {response.status_code}")

        except requests.exceptions.RequestException as e:
            logger.warning(f"[{elapsed}s] Erro de rede ao consultar status: {e}")

        time.sleep(poll_interval)

    logger.error(f"Timeout de {timeout_seconds}s atingido aguardando processamento da tarefa.")
    return None


def get_kie_balance(api_key: str) -> float | None:
    """Consulta o saldo atual de créditos no Kie.ai."""
    url = "https://api.kie.ai/api/v1/chat/credit"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 200:
                balance = float(data.get("data", 0.0))
                logger.info(f"Saldo atual no Kie.ai: {balance:.1f} créditos (~${balance * 0.005:.2f} USD)")
                return balance
    except Exception as e:
        logger.warning(f"Erro ao consultar saldo Kie.ai: {e}")
    return None


def download_video(video_url: str, output_path: Path) -> bool:
    """Baixa o vídeo da URL fornecida e salva no caminho de saída."""
    logger.info(f"Iniciando download do vídeo para: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with requests.get(video_url, stream=True, timeout=60) as response:
            response.raise_for_status()
            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0

            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

            size_mb = downloaded / (1024 * 1024)
            logger.info(f"Download concluído com sucesso: {output_path.name} ({size_mb:.2f} MB)")
            return True

    except Exception as e:
        logger.error(f"Erro ao baixar vídeo de {video_url}: {e}")
        if output_path.exists():
            output_path.unlink()
        return False


def validate_video_file(video_path: Path, min_size_kb: int = 100) -> bool:
    """Valida se o arquivo de vídeo existe e atende ao tamanho mínimo."""
    if not video_path.exists():
        logger.error(f"Arquivo de vídeo não encontrado: {video_path}")
        return False

    size_kb = video_path.stat().st_size / 1024
    if size_kb < min_size_kb:
        logger.error(f"Arquivo de vídeo corrompido ou muito pequeno: {size_kb:.1f} KB (mínimo: {min_size_kb} KB)")
        return False

    logger.info(f"Vídeo validado: {video_path.name} ({size_kb:.1f} KB)")
    return True


def main():
    """Função principal."""
    base_dir = Path(__file__).parent.parent

    # Chave de API do Kie.ai
    api_key = os.environ.get("KIE_API_KEY", "").strip()
    if not api_key:
        logger.error("Chave de API KIE_API_KEY não encontrada nas variáveis de ambiente.")
        sys.exit(1)

    # Parâmetros via variáveis de ambiente (definidos pelo step anterior no Actions)
    script_path = os.environ.get("SCRIPT_PATH", "").strip()
    prompt_visual = os.environ.get("PROMPT_VISUAL", "").strip()

    if not script_path and not prompt_visual:
        logger.error("SCRIPT_PATH ou PROMPT_VISUAL não definidos.")
        sys.exit(1)

    settings = load_config(base_dir)

    # Parâmetros da configuração
    gen_config = settings.get("generation", {})
    video_config = settings.get("video", {})
    model = gen_config.get("model", "grok-imagine/text-to-video")
    resolution = gen_config.get("resolution", "720p")
    duration = int(gen_config.get("duration_seconds", 10))
    aspect_ratio = video_config.get("aspect_ratio", "9:16")
    timeout_seconds = int(gen_config.get("timeout_seconds", 300))
    poll_interval = int(gen_config.get("poll_interval_seconds", 5))

    # Monta o prompt final
    if script_path:
        script_data = load_script(script_path)
        prompt_base = script_data.get("prompt_visual", prompt_visual)
        narracao = script_data.get("narracao", "")
        titulo = script_data.get("titulo", "video")

        # Limpeza de formatação e referências antigas de 15s
        narracao = re.sub(r'[\r\n\s]*(?:---+|\*\*\*+|===+|___+)[\r\n\s]*$', '', narracao).strip().strip('"\'')
        prompt_base = re.sub(r'(?i)exactly\s*15\s*seconds\s*long\.?', '', prompt_base)
        prompt_base = re.sub(r'(?i)15\s*seconds\b', '', prompt_base)
        prompt_base = re.sub(r'\s{2,}', ' ', prompt_base).strip()

        # Se o modelo for Runway ou houver serviço de TTS externo configurado,
        # mantém o prompt puramente visual de alta qualidade culinária
        tts_service = settings.get("tts", {}).get("service")
        if "runway" in model.lower() or tts_service:
            prompt = prompt_base
        elif narracao:
            prompt = f"{prompt_base}\n\nAudio: AI voice speaking in Brazilian Portuguese saying EXACTLY this: '{narracao}'"
        else:
            prompt = prompt_base
    else:
        prompt = prompt_visual
        titulo = "video"

    if not prompt:
        logger.error("Prompt de geração vazio. Abortando pipeline.")
        sys.exit(1)

    # Garante o formato 9:16 no prompt
    if "9:16" not in prompt and "vertical" not in prompt.lower():
        prompt = f"{prompt}, vertical format 9:16, cinematic food quality"

    logger.info("=== INICIANDO GERAÇÃO DE VÍDEO VIA KIE.AI ===")
    logger.info(f"Título: {titulo}")
    logger.info(f"Modelo: {model} ({resolution}, {duration}s, {aspect_ratio})")
    logger.info(f"Prompt ({len(prompt)} caracteres):\n{prompt}\n")

    # Diretório de saída
    output_config = settings.get("output", {})
    videos_dir = base_dir / output_config.get("videos_dir", "output/videos")
    videos_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_titulo = "".join(c for c in titulo if c.isalnum() or c in " _-").strip()[:30]
    video_filename = f"video_{safe_titulo}_{timestamp}.mp4"
    video_output_path = videos_dir / video_filename

    # 1. Cria a tarefa no Kie.ai
    task_id = create_kie_task(
        api_key=api_key,
        prompt=prompt,
        model=model,
        aspect_ratio=aspect_ratio,
        duration=duration,
        resolution=resolution
    )

    if not task_id:
        logger.error("Falha ao criar tarefa no Kie.ai. Abortando pipeline.")
        sys.exit(1)

    # 2. Polling até concluir
    task_result = poll_kie_task(
        api_key=api_key,
        task_id=task_id,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval
    )

    if not task_result:
        logger.error("Falha na geração do vídeo pelo Kie.ai. Abortando pipeline.")
        sys.exit(1)

    video_url = task_result["video_url"]
    credits_spent = task_result.get("credits_consumed", 45.0)
    spent_usd = credits_spent * 0.005

    # 3. Download do vídeo
    success = download_video(video_url, video_output_path)
    if not success:
        logger.error("Falha no download do vídeo gerado. Abortando pipeline.")
        sys.exit(1)

    # 4. Validação do arquivo
    if not validate_video_file(video_output_path):
        logger.error("Arquivo de vídeo inválido ou incompleto. Abortando pipeline.")
        sys.exit(1)

    # 5. Consulta saldo restante após a conclusão
    remaining_credits = get_kie_balance(api_key)
    remaining_usd = (remaining_credits * 0.005) if remaining_credits is not None else 0.0

    # 6. Exporta saída para steps posteriores no GitHub Actions
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"video_path={video_output_path}\n")
            f.write(f"video_filename={video_filename}\n")
            f.write(f"credits_spent={credits_spent:.1f}\n")
            f.write(f"spent_usd={spent_usd:.3f}\n")
            if remaining_credits is not None:
                f.write(f"credits_remaining={remaining_credits:.1f}\n")
                f.write(f"remaining_usd={remaining_usd:.2f}\n")
            else:
                f.write("credits_remaining=N/A\n")
                f.write("remaining_usd=N/A\n")

    logger.info("=== VÍDEO GERADO E VALIDADO COM SUCESSO ===")
    logger.info(f"Arquivo local: {video_output_path}")
    logger.info(f"💰 Créditos gastos: {credits_spent:.1f} (~${spent_usd:.3f} USD)")
    if remaining_credits is not None:
        logger.info(f"💳 Saldo restante: {remaining_credits:.1f} créditos (~${remaining_usd:.2f} USD)")
    print(f"VIDEO_PATH={video_output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
