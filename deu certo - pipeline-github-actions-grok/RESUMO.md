# ✅ Deu Certo — Pipeline GitHub Actions Grok Funcional

**Data:** 06/10/2026
**Projeto:** Gerar Vídeos com Grok

## O que funcionou

A configuração da pipeline completa do GitHub Actions foi um sucesso. O script foi corrigido para:
1. Navegar na página e esperar usando `wait_until="domcontentloaded"` em vez de `networkidle` para evitar timeouts.
2. Identificar e selecionar o botão do "Modo Vídeo" relativo ao botão "Imagem", fugindo do comportamento padrão do Grok que apenas gera imagens.
3. Usar um timeout maior (10 minutos para geração no script e 30 minutos na pipeline).
4. Fazer o download do vídeo gerado diretamente pela sessão logada no Playwright (`page.request.get(video_src)`), porque a tentativa via `urllib` sofria de "HTTP 403 Forbidden".

## Arquivos envolvidos

| Arquivo | Papel na solução |
|---------|-----------------|
| `.github/workflows/video_pipeline.yml` | Teve o `timeout-minutes` aumentado para 30 e os secrets todos mapeados na nuvem. |
| `scripts/generate_video.py` | Recebeu as correções críticas de timeout, clique explícito na toggle "Vídeo" e download através do context do Playwright via request. |
| `config/settings.json` | Teve a configuração de timeout global da geração atualizada para 600 segundos (10 minutos). |

## Como replicar

Sempre que automatizar downloads de CDNs e Cloudfront protegidos na própria sessão onde está, use o `page.request.get()` se tiver acesso ao objeto de contexto do Playwright, pois ele compartilha os Cookies automaticamente e fura a barreira anti-bot, algo que bibliotecas puras (requests, urllib) não fazem sem headers explícitos. E ao mexer com UI de LLMs atualizadas (como o Grok), baseie-se na relação entre elementos ("botão ao lado de 'Imagem'") caso os *aria-labels* e as classes se tornem dinâmicos ou invisíveis.

## Observações

A interface do Grok pode mudar com o tempo (especialmente o botão de Vídeo/Imagem). Se falhar e retornar timeout, baixe a pasta de "screenshots" que configuramos para ficar salva como artefato da Actions e visualize a interface travada!
