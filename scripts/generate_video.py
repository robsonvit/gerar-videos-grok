#!/usr/bin/env python3
"""
generate_video.py
Automatiza a geração de vídeo no Grok Aurora (grok.com/imagine) via Playwright.
Usa a sessão autenticada do usuário armazenada como GitHub Secret (GROK_COOKIES).
"""

import json
import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("ERRO: Playwright não instalado. Execute: pip install playwright && playwright install chromium")
    sys.exit(1)

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


def load_script(script_path: str) -> dict:
    """Carrega o roteiro gerado."""
    path = Path(script_path)
    if not path.exists():
        logger.error(f"Arquivo de roteiro não encontrado: {script_path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def take_screenshot(page, output_dir: Path, label: str):
    """Captura screenshot para diagnóstico."""
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = output_dir / f"screenshot_{label}_{timestamp}.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        logger.info(f"Screenshot salvo: {screenshot_path}")
    except Exception as e:
        logger.warning(f"Falha ao capturar screenshot: {e}")


def load_cookies_from_env() -> list | None:
    """Carrega cookies do Grok a partir da variável de ambiente GROK_COOKIES."""
    cookies_json = os.environ.get("GROK_COOKIES", "")
    if not cookies_json:
        logger.warning("Variável GROK_COOKIES não encontrada. Executando sem cookies.")
        return None
    try:
        cookies = json.loads(cookies_json)
        logger.info(f"Cookies carregados: {len(cookies)} cookie(s)")
        return cookies
    except json.JSONDecodeError as e:
        logger.error(f"GROK_COOKIES inválido (não é JSON válido): {e}")
        return None


def wait_for_video_ready(page, timeout_ms: int, poll_interval_ms: int, screenshot_dir: Path, existing_srcs: set = None) -> str | None:
    """
    Aguarda o vídeo ficar disponível na interface do Grok.
    Retorna a URL do vídeo ou None em caso de timeout.

    ATENÇÃO: Os seletores abaixo devem ser atualizados se a interface do Grok mudar.
    Verifique os seletores em: config/settings.json -> generation.selectors
    """
    logger.info("Aguardando geração do vídeo...")
    start_time = time.time()
    timeout_s = timeout_ms / 1000
    
    if existing_srcs is None:
        existing_srcs = set()

    while (time.time() - start_time) < timeout_s:
        try:
            # Tenta localizar elemento de vídeo gerado
            # SELETOR: Atualizar se a interface mudar
            video_elements = page.query_selector_all("video, video source, source")
            for video in video_elements:
                src = video.get_attribute("src")
                if src and ("blob:" in src or ".mp4" in src or "media" in src.lower()):
                    if src not in existing_srcs:
                        logger.info(f"Vídeo detectado com src: {src[:80]}...")
                        return src

            # Verifica se há mensagem de erro na página
            error_texts = [
                "Something went wrong",
                "Error generating",
                "Failed to generate",
                "Unable to create"
            ]
            page_content = page.content().lower()
            for error_text in error_texts:
                if error_text.lower() in page_content:
                    logger.error(f"Erro detectado na página: '{error_text}'")
                    take_screenshot(page, screenshot_dir, "error_detected")
                    return None

            elapsed = int(time.time() - start_time)
            logger.info(f"Aguardando... {elapsed}s / {int(timeout_s)}s")
            time.sleep(poll_interval_ms / 1000)

        except Exception as e:
            logger.warning(f"Erro durante polling: {e}")
            time.sleep(poll_interval_ms / 1000)

    logger.error(f"Timeout após {int(timeout_s)}s aguardando o vídeo")
    take_screenshot(page, screenshot_dir, "timeout")
    return None


def download_video(page, video_src: str, output_path: Path) -> bool:
    """Faz o download do vídeo gerado."""
    import urllib.request

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if video_src.startswith("blob:"):
            # Para URLs blob, usa JavaScript para extrair o conteúdo
            logger.info("Detectada URL blob, extraindo via JavaScript...")
            video_data = page.evaluate("""
                async (src) => {
                    const response = await fetch(src);
                    const buffer = await response.arrayBuffer();
                    const bytes = new Uint8Array(buffer);
                    return Array.from(bytes);
                }
            """, video_src)

            if video_data:
                with open(output_path, "wb") as f:
                    f.write(bytes(video_data))
                logger.info(f"Vídeo blob salvo em: {output_path}")
                return True
            else:
                logger.error("Dados do blob vazio")
                return False

        elif video_src.startswith("http"):
            # Download direto para URLs HTTP
            logger.info(f"Fazendo download direto de: {video_src[:80]}...")
            response = page.request.get(video_src)
            if response.ok:
                with open(output_path, "wb") as f:
                    f.write(response.body())
                logger.info(f"Vídeo salvo em: {output_path}")
                return True
            else:
                logger.error(f"Erro ao baixar vídeo. Status: {response.status} - {response.status_text}")
                return False

        else:
            logger.error(f"Tipo de URL não suportado: {video_src[:50]}")
            return False

    except Exception as e:
        logger.error(f"Erro ao fazer download do vídeo: {e}")
        return False


def generate_video_on_grok(
    prompt: str,
    output_path: Path,
    settings: dict,
    screenshot_dir: Path
) -> bool:
    """
    Automatiza a geração de vídeo no Grok Aurora.

    Parâmetros configuráveis em config/settings.json -> generation
    """
    gen_config = settings.get("generation", {})
    url = gen_config.get("url", "https://grok.com/imagine")
    timeout_s = gen_config.get("timeout_seconds", 300)
    poll_interval_s = gen_config.get("poll_interval_seconds", 15)
    max_retries = gen_config.get("max_retries", 3)
    retry_delay_s = gen_config.get("retry_delay_seconds", 30)
    headless = gen_config.get("headless", True)
    screenshot_on_error = gen_config.get("screenshot_on_error", True)

    cookies = load_cookies_from_env()

    for attempt in range(1, max_retries + 1):
        logger.info(f"=== Tentativa {attempt}/{max_retries} de geração de vídeo ===")

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=headless,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu"
                    ]
                )

                context = browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                )

                # Adiciona cookies se disponíveis
                if cookies:
                    context.add_cookies(cookies)
                    logger.info("Cookies de autenticação aplicados")

                page = context.new_page()

                page.goto(url, wait_until="domcontentloaded", timeout=60000)

                if screenshot_on_error:
                    take_screenshot(page, screenshot_dir, f"page_loaded_attempt{attempt}")

                # Aguarda o campo de input aparecer
                # SELETOR: Atualizar se a interface mudar
                logger.info("Aguardando campo de input...")
                try:
                    page.wait_for_selector(
                        "textarea, [contenteditable='true']",
                        timeout=30000
                    )
                except PlaywrightTimeout:
                    logger.warning("Campo de input não encontrado. Pode ser necessário autenticação.")
                    if screenshot_on_error:
                        take_screenshot(page, screenshot_dir, f"no_input_attempt{attempt}")
                    browser.close()
                    if attempt < max_retries:
                        time.sleep(retry_delay_s)
                    continue

                # Insere o prompt
                logger.info(f"Inserindo prompt ({len(prompt)} chars)...")
                input_selector = "textarea, [contenteditable='true']"
                page.fill(input_selector, prompt)
                time.sleep(1)

                # Garante que o modo Vídeo está selecionado
                # SELETOR: O botão de vídeo fica ao lado do botão de Imagem
                try:
                    video_button = page.query_selector("button:has-text('Imagem') + button")
                    if video_button:
                        video_button.click()
                        logger.info("Modo Vídeo selecionado")
                        time.sleep(0.5)
                        
                        # Seleciona 15s usando locator exato do botão de duração
                        try:
                            # O botão real tem o aria-label 'Duração do vídeo'
                            btn_duration = page.locator("[aria-label='Duração do vídeo'], [title='Duração do vídeo']").first
                            if btn_duration.is_visible(timeout=1000):
                                text_now = btn_duration.inner_text().strip()
                                if '15' in text_now:
                                    logger.info("O vídeo já está configurado para 15s.")
                                else:
                                    btn_duration.click(force=True)
                                    logger.info(f"Menu de duração aberto. Estava em '{text_now}'.")
                                    time.sleep(1)
                                    
                                    # Agora clica em 15s no menu aberto
                                    btn_15s = page.locator("text='15s'").last
                                    if btn_15s.is_visible(timeout=1000):
                                        btn_15s.click(force=True)
                                        logger.info("Opção 15s selecionada com sucesso!")
                                    else:
                                        logger.warning("Opção 15s não visível no menu.")
                            else:
                                logger.warning("Botão de 'Duração do vídeo' não encontrado pelo aria-label.")
                        except Exception as inner_e:
                            logger.warning(f"Erro ao selecionar duração de 15s: {inner_e}")
                            
                except Exception as e:
                    logger.warning(f"Não foi possível selecionar modo vídeo: {e}")

                # Coleta vídeos já existentes na página para ignorá-los
                existing_srcs = set()
                try:
                    video_els = page.query_selector_all("video, video source, source")
                    for el in video_els:
                        src = el.get_attribute("src")
                        if src: existing_srcs.add(src)
                except Exception as e:
                    pass
                logger.info(f"Encontrados {len(existing_srcs)} vídeos antigos na página para ignorar.")

                # Envia o prompt
                # SELETOR: Botão de envio
                logger.info("Enviando prompt...")
                try:
                    send_button = page.query_selector(
                        "button[type='submit'], button[aria-label*='Send'], button[aria-label*='Enviar']"
                    )
                    if send_button:
                        send_button.click()
                    else:
                        page.keyboard.press("Enter")
                except Exception:
                    page.keyboard.press("Enter")

                time.sleep(2)

                if screenshot_on_error:
                    take_screenshot(page, screenshot_dir, f"after_submit_attempt{attempt}")

                # Aguarda vídeo ficar pronto
                video_src = wait_for_video_ready(
                    page=page,
                    timeout_ms=timeout_s * 1000,
                    poll_interval_ms=poll_interval_s * 1000,
                    screenshot_dir=screenshot_dir,
                    existing_srcs=existing_srcs
                )

                if video_src:
                    success = download_video(page, video_src, output_path)
                    browser.close()

                    if success:
                        logger.info(f"Vídeo gerado e salvo com sucesso: {output_path}")
                        return True
                    else:
                        logger.error("Falha no download do vídeo")
                else:
                    logger.error("Vídeo não encontrado na página")
                    browser.close()

        except Exception as e:
            logger.error(f"Erro durante automação do navegador (tentativa {attempt}): {e}")
            if screenshot_on_error:
                try:
                    take_screenshot(page, screenshot_dir, f"exception_attempt{attempt}")
                except Exception:
                    pass

        if attempt < max_retries:
            logger.info(f"Aguardando {retry_delay_s}s antes da próxima tentativa...")
            time.sleep(retry_delay_s)

    logger.error(f"Todas as {max_retries} tentativas falharam")
    return False


def validate_video_file(video_path: Path, min_size_kb: int = 100) -> bool:
    """Valida se o arquivo de vídeo existe e tem tamanho mínimo."""
    if not video_path.exists():
        logger.error(f"Arquivo de vídeo não encontrado: {video_path}")
        return False

    size_kb = video_path.stat().st_size / 1024
    if size_kb < min_size_kb:
        logger.error(f"Arquivo de vídeo muito pequeno: {size_kb:.1f} KB (mínimo: {min_size_kb} KB)")
        return False

    logger.info(f"Vídeo validado: {video_path.name} ({size_kb:.1f} KB)")
    return True


def main():
    """Função principal."""
    base_dir = Path(__file__).parent.parent

    # Parâmetros via variáveis de ambiente (definidos pelo step anterior no Actions)
    script_path = os.environ.get("SCRIPT_PATH", "")
    prompt_visual = os.environ.get("PROMPT_VISUAL", "")

    if not script_path and not prompt_visual:
        logger.error("SCRIPT_PATH ou PROMPT_VISUAL não definidos.")
        logger.error("Defina pelo menos PROMPT_VISUAL como variável de ambiente.")
        sys.exit(1)

    settings = load_config(base_dir)

    # Obtém o prompt visual
    if script_path:
        script_data = load_script(script_path)
        prompt = script_data.get("prompt_visual", prompt_visual)
        titulo = script_data.get("titulo", "video")
    else:
        prompt = prompt_visual
        titulo = "video"

    if not prompt:
        logger.error("Prompt visual vazio. Não é possível gerar o vídeo.")
        sys.exit(1)

    # Adiciona configurações de formato ao prompt se não presentes
    if "9:16" not in prompt and "vertical" not in prompt.lower():
        prompt = f"{prompt}, vertical format 9:16, cinematic quality, 15 seconds"

    logger.info("=== INICIANDO GERAÇÃO DE VÍDEO ===")
    logger.info(f"Título: {titulo}")
    logger.info(f"Prompt: {prompt[:100]}...")

    # Configura diretórios de saída
    output_config = settings.get("output", {})
    videos_dir = base_dir / output_config.get("videos_dir", "output/videos")
    screenshots_dir = base_dir / output_config.get("screenshots_dir", "output/screenshots")
    videos_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_titulo = "".join(c for c in titulo if c.isalnum() or c in " _-").strip()[:30]
    video_filename = f"video_{safe_titulo}_{timestamp}.mp4"
    video_output_path = videos_dir / video_filename

    # Gera o vídeo
    success = generate_video_on_grok(
        prompt=prompt,
        output_path=video_output_path,
        settings=settings,
        screenshot_dir=screenshots_dir
    )

    if not success:
        logger.error("Falha na geração do vídeo. Abortando pipeline.")
        sys.exit(1)

    # Valida o arquivo gerado
    if not validate_video_file(video_output_path):
        logger.error("Arquivo de vídeo inválido. Abortando pipeline.")
        sys.exit(1)

    # Exporta caminho para o próximo step
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"video_path={video_output_path}\n")
            f.write(f"video_filename={video_filename}\n")

    logger.info("=== VÍDEO GERADO COM SUCESSO ===")
    logger.info(f"Arquivo: {video_output_path}")
    print(f"VIDEO_PATH={video_output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
