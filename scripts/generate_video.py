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


def dismiss_popups(page, screenshot_dir: Path, label: str = "popup"):
    """
    Fecha qualquer popup/modal que esteja bloqueando a interface do Grok.
    Exemplos: 'Conheça o Bot do Grok', 'Shape your scene', banners de novidades, etc.
    """
    dismissed = False

    # Estratégia 1: Clica em botões de confirmação/fechamento conhecidos
    action_selectors = [
        "button:has-text('Comece agora')",
        "button:has-text('Começar')",
        "button:has-text('Get started')",
        "button:has-text('Start now')",
        "button:has-text('Try it now')",
        "button[aria-label='Close']",
        "button[aria-label='Fechar']",
        "button[aria-label='close']",
        "button[title='Close']",
        "button[title='Fechar']",
        "[role='dialog'] button",
        "[data-testid='close-button']",
    ]
    for selector in action_selectors:
        try:
            btns = page.query_selector_all(selector)
            for btn in btns:
                if btn.is_visible():
                    btn.click(force=True)
                    time.sleep(0.3)
                    dismissed = True
                    logger.info(f"Botão de popup acionado via seletor: {selector}")
        except Exception:
            continue

    # Estratégia 2: Pressiona Escape
    try:
        page.keyboard.press("Escape")
        time.sleep(0.3)
    except Exception:
        pass

    # Estratégia 3: Remoção direta via JavaScript (infalível para modais e backdrops persistentes)
    try:
        removed_count = page.evaluate("""() => {
            let count = 0;
            // 1. Tenta clicar em botões dentro do dialog
            document.querySelectorAll('[role="dialog"], dialog').forEach(d => {
                d.querySelectorAll('button').forEach(b => {
                    const txt = (b.innerText || '').toLowerCase();
                    const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                    if (txt.includes('comece') || txt.includes('fechar') || txt.includes('close') ||
                        aria.includes('close') || aria.includes('fechar') || txt.includes('try it')) {
                        try { b.click(); count++; } catch (e) {}
                    }
                });
            });
            // 2. Remove modais e overlays do DOM se ainda existirem
            document.querySelectorAll('[role="dialog"], dialog, [data-state="open"]').forEach(el => {
                el.remove();
                count++;
            });
            // 3. Remove backdrops que possam bloquear cliques
            document.querySelectorAll('div[class*="backdrop"], div[class*="overlay"]').forEach(el => {
                el.remove();
                count++;
            });
            // 4. Restaura pointer-events e overflow da página
            if (document.body) {
                document.body.style.pointerEvents = 'auto';
                document.body.style.overflow = 'auto';
            }
            return count;
        }""")
        if removed_count > 0:
            logger.info(f"Remoção via JS eliminou/acionou {removed_count} elemento(s) de modal/backdrop")
            dismissed = True
    except Exception as e:
        logger.warning(f"Falha na remoção de popup via JS: {e}")

    # Verifica se ainda há modal visível
    try:
        modal = page.query_selector("[role='dialog']")
        if modal and modal.is_visible():
            logger.warning("Modal ainda visível após todas as tentativas")
            take_screenshot(page, screenshot_dir, f"{label}_modal_persistente")
        else:
            if dismissed:
                logger.info("✅ Popup/modal fechado/removido com sucesso")
    except Exception:
        pass


def select_video_mode(page, max_retries: int = 5) -> bool:
    """
    Garante que o modo Vídeo está selecionado na interface do Grok Aurora.
    Retorna True se confirmado que está em modo vídeo, False caso contrário.
    """
    logger.info("Verificando e selecionando modo Vídeo...")
    duration_locator = page.locator("[aria-label*='uração do vídeo' i], [title*='uração do vídeo' i], [aria-label*='ideo duration' i]").first

    for attempt in range(1, max_retries + 1):
        try:
            # 1. Verifica se já está em modo vídeo (ex: botão de duração já está visível)
            if duration_locator.is_visible(timeout=1000):
                logger.info("✅ Modo Vídeo já está ativo (botão de duração presente)")
                return True

            # 2. Tenta clicar no botão de vídeo via múltiplos seletores Playwright com auto-wait
            clicked = False
            video_locators = [
                "button:has-text('Imagem') + button",
                "button:has-text('Imagem') ~ button",
                "button[aria-label*='ideo' i]",
                "button[title*='ideo' i]",
                "button:has-text('Vídeo')",
                "button:has-text('Video')",
            ]

            for loc in video_locators:
                try:
                    btn = page.locator(loc).first
                    if btn.is_visible(timeout=1500):
                        btn.click(force=True)
                        logger.info(f"Botão de modo Vídeo clicado via locator: {loc}")
                        clicked = True
                        time.sleep(1)
                        break
                except Exception:
                    continue

            # 3. Fallback: injeção JavaScript robusta
            if not clicked:
                js_clicked = page.evaluate("""() => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const vBtn = buttons.find(b => {
                        const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                        const txt = (b.innerText || '').toLowerCase();
                        const title = (b.getAttribute('title') || '').toLowerCase();
                        return aria.includes('video') || aria.includes('vídeo') ||
                               txt.includes('video') || txt.includes('vídeo') ||
                               title.includes('video') || title.includes('vídeo');
                    });
                    if (vBtn) {
                        vBtn.click();
                        return 'video_button';
                    }
                    const imgBtn = buttons.find(b => (b.innerText || '').toLowerCase().includes('imagem'));
                    if (imgBtn) {
                        let next = imgBtn.nextElementSibling;
                        while (next && next.tagName !== 'BUTTON') next = next.nextElementSibling;
                        if (!next && imgBtn.parentElement) {
                            const siblings = Array.from(imgBtn.parentElement.querySelectorAll('button'));
                            const idx = siblings.indexOf(imgBtn);
                            if (idx !== -1 && idx + 1 < siblings.length) next = siblings[idx + 1];
                        }
                        if (next) {
                            next.click();
                            return 'sibling_button';
                        }
                    }
                    return null;
                }""")
                if js_clicked:
                    logger.info(f"Modo Vídeo acionado via JS: {js_clicked}")
                    time.sleep(1)

            # 4. Confirma se o modo Vídeo foi ativado
            if duration_locator.is_visible(timeout=2500):
                logger.info("✅ Modo Vídeo confirmado ativo!")
                return True
        except Exception as e:
            logger.warning(f"Tentativa {attempt} ao selecionar modo Vídeo: {e}")

        time.sleep(1)

    logger.warning("Não foi possível confirmar ativação do modo Vídeo após várias tentativas")
    return False


def select_duration_15s(page) -> bool:
    """Seleciona a duração de 15 segundos no menu de duração do vídeo."""
    logger.info("Configurando duração do vídeo para 15s...")
    try:
        duration_btn = page.locator("[aria-label*='uração do vídeo' i], [title*='uração do vídeo' i], [aria-label*='ideo duration' i]").first
        if not duration_btn.is_visible(timeout=2000):
            fallback_btn = page.locator("button:has-text('5s'), button:has-text('6s'), button:has-text('10s'), button:has-text('15s')").first
            if fallback_btn.is_visible(timeout=2000):
                duration_btn = fallback_btn

        if duration_btn.is_visible(timeout=2000):
            text_now = duration_btn.inner_text().strip()
            logger.info(f"Botão de duração encontrado. Valor atual: '{text_now}'")
            if '15' in text_now:
                logger.info("Duração já está configurada para 15s.")
                return True

            duration_btn.click(force=True)
            logger.info("Menu de duração aberto. Aguardando opções...")
            time.sleep(1)

            opt_15s = page.locator("[role='menuitem']:has-text('15s'), button:has-text('15s'), text='15s'").last
            if opt_15s.is_visible(timeout=3000):
                opt_15s.click(force=True)
                logger.info("✅ Duração de 15s selecionada com sucesso!")
                time.sleep(0.5)
                return True
            else:
                all_els = page.locator("text=15s").all()
                if all_els:
                    all_els[-1].click(force=True)
                    logger.info("✅ Duração de 15s selecionada via fallback!")
                    time.sleep(0.5)
                    return True
                logger.warning("Opção 15s não encontrada no menu.")
        else:
            logger.warning("Botão de duração não encontrado.")
    except Exception as e:
        logger.warning(f"Erro ao selecionar duração de 15s: {e}")
    return False


def wait_for_video_ready(
    page,
    timeout_ms: int,
    poll_interval_ms: int,
    screenshot_dir: Path,
    existing_srcs: set = None,
    captured_urls: list = None
) -> str | None:
    """
    Aguarda o vídeo ficar disponível na interface do Grok.
    Retorna a URL do vídeo ou None em caso de timeout.
    """
    logger.info("Aguardando geração do vídeo...")
    start_time = time.time()
    timeout_s = timeout_ms / 1000

    if existing_srcs is None:
        existing_srcs = set()
    if captured_urls is None:
        captured_urls = []

    while (time.time() - start_time) < timeout_s:
        try:
            # 1. Verifica se interceptamos URL de vídeo via rede
            for url in captured_urls:
                if url and url not in existing_srcs:
                    logger.info(f"🎯 Vídeo detectado via tráfego de rede: {url[:80]}...")
                    return url

            # 2. Tenta localizar elemento de vídeo gerado no DOM
            video_elements = page.query_selector_all("video, video source, source")
            for video in video_elements:
                src = video.get_attribute("src")
                if src and ("blob:" in src or ".mp4" in src or "media" in src.lower()):
                    if src not in existing_srcs:
                        logger.info(f"Vídeo detectado com src: {src[:80]}...")
                        return src

            # 3. Verifica via JavaScript (currentSrc e src em <video>)
            js_src = page.evaluate("""() => {
                for (const v of document.querySelectorAll('video')) {
                    const s = v.currentSrc || v.src;
                    if (s && (s.includes('blob:') || s.includes('.mp4') || s.toLowerCase().includes('media'))) {
                        return s;
                    }
                }
                return null;
            }""")
            if js_src and js_src not in existing_srcs:
                logger.info(f"Vídeo detectado via currentSrc (JS): {js_src[:80]}...")
                return js_src

            # 4. Tenta clicar em botões de play / preview gerados após 30s
            if int(time.time() - start_time) > 30:
                try:
                    page.evaluate("""() => {
                        const playBtns = document.querySelectorAll("button[aria-label*='Play' i], button[aria-label*='Reproduzir' i], [role='button'] svg");
                        if (playBtns.length > 0) {
                            try { playBtns[0].closest('button, [role=\"button\"]').click(); } catch (e) {}
                        }
                    }""")
                except Exception:
                    pass

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
                time.sleep(2)  # Aguarda JS renderizar completamente

                # Fecha qualquer popup/modal que apareça ao carregar
                # Ex: "Conheça o Grok Bot", banners de novidades, etc.
                logger.info("Verificando e fechando popups iniciais...")
                dismiss_popups(page, screenshot_dir, f"initial_attempt{attempt}")
                time.sleep(1)

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
                    logger.warning("Campo de input não encontrado. Tentando fechar popups e aguardar novamente...")
                    dismiss_popups(page, screenshot_dir, f"retry_popup_attempt{attempt}")
                    time.sleep(2)
                    try:
                        page.wait_for_selector(
                            "textarea, [contenteditable='true']",
                            timeout=15000
                        )
                    except PlaywrightTimeout:
                        logger.warning("Campo de input ainda não encontrado. Pode ser necessário autenticação.")
                        if screenshot_on_error:
                            take_screenshot(page, screenshot_dir, f"no_input_attempt{attempt}")
                        browser.close()
                        if attempt < max_retries:
                            time.sleep(retry_delay_s)
                        continue

                # Registra listener para capturar URLs de vídeo pelo tráfego de rede
                captured_video_urls = []
                def on_network_response(resp):
                    try:
                        r_url = resp.url
                        ct = (resp.headers.get("content-type") or "").lower()
                        if (".mp4" in r_url or "video" in ct) and not r_url.endswith(".m3u8"):
                            if r_url not in captured_video_urls:
                                logger.info(f"🌐 Interceptada URL de vídeo na rede: {r_url[:80]}...")
                                captured_video_urls.append(r_url)
                    except Exception:
                        pass

                page.on("response", on_network_response)

                # Garante modo Vídeo e duração de 15s antes de inserir o prompt
                select_video_mode(page)
                select_duration_15s(page)

                # Insere o prompt usando locator nativo (auto-wait e resiliente a re-render)
                logger.info(f"Inserindo prompt ({len(prompt)} chars)...")
                input_selector = "textarea, [contenteditable='true']"
                page.locator(input_selector).first.fill(prompt)
                time.sleep(1)

                # Confirma modo Vídeo e 15s após digitação do prompt
                select_video_mode(page)
                select_duration_15s(page)

                # Coleta vídeos já existentes na página para ignorá-los
                existing_srcs = set()
                try:
                    video_els = page.query_selector_all("video, video source, source")
                    for el in video_els:
                        src = el.get_attribute("src")
                        if src:
                            existing_srcs.add(src)
                except Exception as e:
                    pass
                logger.info(f"Encontrados {len(existing_srcs)} vídeos antigos na página para ignorar.")

                # Garante que nenhum popup novo apareceu antes do envio
                dismiss_popups(page, screenshot_dir, f"before_submit_attempt{attempt}")
                time.sleep(0.5)

                # Envia o prompt
                logger.info("Enviando prompt...")
                try:
                    send_btn = page.locator("button[type='submit'], button[aria-label*='Send' i], button[aria-label*='Enviar' i]").first
                    if send_btn.is_visible(timeout=2000):
                        send_btn.click(force=True)
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
                    existing_srcs=existing_srcs,
                    captured_urls=captured_video_urls
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
        prompt_base = script_data.get("prompt_visual", prompt_visual)
        narracao = script_data.get("narracao", "")
        titulo = script_data.get("titulo", "video")
        
        # Junta a narração ao prompt visual para o Grok falar o texto exato
        if narracao:
            prompt = f"{prompt_base}\n\nAudio: AI voice speaking in Brazilian Portuguese saying EXACTLY this: '{narracao}'"
        else:
            prompt = prompt_base
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
