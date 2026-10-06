#!/usr/bin/env python3
"""
export_cookies.py
Script auxiliar para exportar os cookies do Grok do seu navegador local.

USO:
1. Faça login no grok.com no seu navegador normalmente
2. Execute este script com o Playwright apontando para seu perfil de usuário
3. Copie o JSON resultante e cole no GitHub Secret GROK_COOKIES

ALTERNATIVA MANUAL:
- Use uma extensão de navegador como "EditThisCookie" ou "Cookie-Editor"
- Exporte os cookies de grok.com no formato JSON
- Cole o resultado no GitHub Secret GROK_COOKIES

IMPORTANTE:
- Seus cookies são credenciais pessoais. Nunca compartilhe com ninguém.
- Configure como GitHub Secret (não como variável comum).
- Os cookies expiram periodicamente. Você precisará renová-los.
"""

import json
import os
import sys
from pathlib import Path


def export_cookies_via_playwright():
    """
    Exporta cookies usando Playwright com seu perfil de navegador existente.
    Requer que você já esteja logado no grok.com no Chrome/Edge.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERRO: Playwright não instalado.")
        print("Execute: pip install playwright && playwright install chromium")
        sys.exit(1)

    # Caminho do perfil do Chrome no Windows
    chrome_profile_paths = [
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\User Data"),
        os.path.expanduser(r"~\AppData\Local\Microsoft\Edge\User Data"),
    ]

    user_data_dir = None
    for path in chrome_profile_paths:
        if os.path.exists(path):
            user_data_dir = path
            print(f"Perfil encontrado em: {path}")
            break

    if not user_data_dir:
        print("Perfil de navegador não encontrado. Usando sessão nova.")
        print("Você precisará fazer login manualmente quando o navegador abrir.")

    with sync_playwright() as p:
        if user_data_dir:
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                channel="chrome"
            )
        else:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()

        page = context.new_page()
        page.goto("https://grok.com/imagine")

        print("\n" + "="*60)
        print("INSTRUÇÕES:")
        print("1. Faça login no Grok se ainda não estiver logado")
        print("2. Aguarde carregar completamente")
        print("3. Pressione ENTER aqui no terminal quando estiver pronto")
        print("="*60)
        input("\nPressione ENTER após fazer login no Grok...")

        cookies = context.cookies(["https://grok.com"])
        context.close()

    if not cookies:
        print("AVISO: Nenhum cookie encontrado para grok.com")
        sys.exit(1)

    cookies_json = json.dumps(cookies, indent=2, ensure_ascii=False)

    # Salva em arquivo local (NÃO commitar este arquivo!)
    output_path = Path("grok_cookies_PRIVADO.json")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(cookies_json)

    print(f"\n✅ {len(cookies)} cookie(s) exportado(s)")
    print(f"📄 Salvo em: {output_path.absolute()}")
    print("\n⚠️  IMPORTANTE:")
    print("1. Copie o conteúdo de grok_cookies_PRIVADO.json")
    print("2. Cole no GitHub Secret chamado GROK_COOKIES")
    print("3. NÃO commite este arquivo no repositório!")
    print("4. O .gitignore já ignora arquivos *PRIVADO*")

    # Exibe resumo dos cookies (sem valores sensíveis)
    print("\nCookies encontrados:")
    for cookie in cookies:
        name = cookie.get("name", "")
        domain = cookie.get("domain", "")
        print(f"  - {name} ({domain})")

    return cookies_json


def show_manual_instructions():
    """Exibe instruções para exportar cookies manualmente."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║        EXPORTAR COOKIES DO GROK - INSTRUÇÕES MANUAIS        ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  MÉTODO 1: Extensão do Navegador (Recomendado)              ║
║                                                              ║
║  1. Instale a extensão "Cookie-Editor" no Chrome/Edge       ║
║  2. Acesse grok.com e faça login                            ║
║  3. Clique no ícone da extensão                             ║
║  4. Clique em "Export" → "Export as JSON"                   ║
║  5. Copie o JSON                                            ║
║  6. Cole no GitHub Secret: GROK_COOKIES                     ║
║                                                              ║
║  MÉTODO 2: DevTools (Avançado)                              ║
║                                                              ║
║  1. Acesse grok.com no Chrome                               ║
║  2. Pressione F12 (DevTools)                                ║
║  3. Vá em Application → Cookies → grok.com                  ║
║  4. Copie os valores necessários                            ║
║                                                              ║
║  FORMATO ESPERADO (JSON array):                             ║
║  [                                                          ║
║    {                                                        ║
║      "name": "session",                                     ║
║      "value": "xxx",                                        ║
║      "domain": ".grok.com",                                 ║
║      "path": "/"                                            ║
║    }                                                        ║
║  ]                                                          ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--manual":
        show_manual_instructions()
    else:
        print("🍪 Exportador de Cookies do Grok")
        print("Use --manual para ver instruções manuais\n")
        export_cookies_via_playwright()
