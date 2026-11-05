# ✅ Deu Certo — Migração para Kie.ai (Grok Imagine 720p 10s com Narração PT-BR)

**Data:** 05/11/2026 20:20
**Projeto:** GERAR VÍDEOS COM GROK

## O que funcionou

A migração completa da geração de vídeos do Grok Imagine para a API oficial do Kie.ai foi implementada e testada com sucesso no GitHub Actions.
Anteriormente, o projeto dependia de automação de navegador via Playwright/Chromium com cookies de sessão (`GROK_COOKIES`), o que causava expirações frequentes, falhas com pop-ups e lentidão no runner.
Com a migração para o endpoint REST do Kie.ai utilizando o modelo `grok-imagine/text-to-video`, os vídeos são gerados em alta fidelidade culinária vertical 9:16 a 720p, com 10 segundos de duração e narração audível nativa em português brasileiro (PT-BR), consumindo apenas 45 créditos (~$0,22) por vídeo em ~55 segundos.

## Arquivos envolvidos

| Arquivo | Papel na solução |
|---------|-----------------|
| `generate_video.py` | Cliente Python da API Kie.ai: cria a tarefa (`createTask`), faz polling (`recordInfo`), baixa o vídeo e valida o arquivo gerado. |
| `generate_script.py` | Gerador e validador de roteiro culinário: ajustado para 10 segundos (`0-3s`, `3-7s`, `7-10s`) e narração calibrada entre 30 e 40 palavras. |
| `settings.json` | Configurações do pipeline: serviço `kie.ai`, modelo `grok-imagine/text-to-video`, resolução `720p`, duração `10s`. |
| `master_prompt.txt` | Prompt mestre culinário calibrado para 10 segundos e narração em PT-BR. |
| `requirements.txt` | Removido `playwright`, mantido apenas `requests>=2.31.0`. |
| `video_pipeline.yml` | Workflow do GitHub Actions sem instalação pesada de Chromium, autenticado via `KIE_API_KEY`. |
| `KNOWLEDGE_KIE_AI.md` | Guia técnico com endpoints, formatos de payload e modelos do Kie.ai. |

## Como replicar

1. Adicionar o secret `KIE_API_KEY` nas configurações do repositório no GitHub (`Settings` -> `Secrets and variables` -> `Actions`).
2. Configurar o payload de criação de tarefa em `generate_video.py` com o modelo `grok-imagine/text-to-video`, duração `10`, aspect_ratio `9:16`, resolução `720p`.
3. Adicionar no prompt a instrução de áudio:
   `Audio: AI voice speaking in Brazilian Portuguese saying EXACTLY this: '<narracao>'`
4. Fazer polling no endpoint `https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<id>` a cada 5s até `state == "success"`.
5. Baixar o arquivo a partir de `resultUrls[0]` e processar com FFmpeg (`loudnorm` EBU R128 + H.264 vertical).

## Observações

- O modelo `grok-imagine/text-to-video` no Kie.ai custa 45 créditos ($0,225) para 10 segundos em 720p.
- A consulta de saldo pode ser feita via `GET https://api.kie.ai/api/v1/chat/credit`.
- 1 crédito Kie.ai equivale a $0,005 USD (200 créditos = $1,00 USD).
