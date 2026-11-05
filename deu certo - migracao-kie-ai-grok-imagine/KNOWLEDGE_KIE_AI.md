# Conhecimento: Kie.ai API Platform

**Última atualização:** 2026-11-05
**Fonte:** [Kie.ai Docs](https://docs.kie.ai/) & [Kie.ai Pricing](https://kie.ai/pricing)

## Visão Geral
A Kie.ai é uma plataforma unificada de APIs para geração de mídia por IA (vídeo, áudio, imagem e texto), com modelo de cobrança pré-pago baseado em créditos (1 crédito ≈ US$ 0,005).

## Autenticação e Endpoints Principais

* **Base URL:** `https://api.kie.ai`
* **Header de Autenticação:**
  ```http
  Authorization: Bearer <KIE_API_KEY>
  Content-Type: application/json
  ```
* **Consultar Créditos:**
  `GET /api/v1/chat/credit`
  Retorna: `{"code": 200, "data": <saldo_creditos>}`

* **Criar Tarefa de Geração (Assíncrona):**
  `POST /api/v1/jobs/createTask`
  Retorna: `{"code": 200, "data": {"taskId": "...", "recordId": "..."}}`

* **Consultar Status da Tarefa:**
  `GET /api/v1/jobs/recordInfo?taskId=<taskId>`
  Estados: `waiting` -> `queuing` -> `generating` -> `success` / `fail`

## Modelos de Vídeo e Comparativo de Custo / Qualidade

| Modelo | Resoluções | Duração | Custo Estimado (10s 720p) | Suporte a Áudio / Voz Nativa | Fidelidade a Receitas |
|---|---|---|---|---|---|
| **`grok-imagine/text-to-video`** | 480p, 720p, 1080p | 6s a 15s | **45 créditos (~$0,22)** | **SIM (Voz e Efeitos nativos)** | **Excelente (mesmo motor Grok Aurora)** |
| `wan/2-6-text-to-video` | 720p, 1080p | 5s | ~160 créditos (~$0,80) | Não | Média/Boa |
| `kling-2.6/text-to-video` | 720p, 1080p | 5s, 10s | ~170 créditos (~$0,85) | Opcional | Alta |
| `minimax-h3/text-to-video` | 720p, 1080p | 6s | ~180 créditos (~$0,90) | Parcial | Boa |
| `bytedance/v1-lite-text-to-video` | 480p, 720p | 5s | ~630 créditos (~$3,15) | Não | Boa |

## Modelo Escolhido: `grok-imagine/text-to-video`

* **Vantagens:**
  1. **Melhor preço absoluto:** 45 créditos para 10 segundos em 720p (~US$ 0,22 por vídeo).
  2. **Compatibilidade 100%:** Nossos prompts e diretrizes visuais já foram lapidados especificamente para a sintaxe do Grok Aurora.
  3. **Narração em Português Nativa:** Gera áudio sincronizado com a instrução `Audio: AI voice speaking in Brazilian Portuguese saying EXACTLY this: '...'`.
  4. **Sem necessidade de Playwright / Headless Browser / Cookies:** A geração é feita por chamada REST API direta em segundos, sem risco de expiração de cookies, seletores quebrados ou paywalls de interface web.

## Formato do Payload

```json
{
  "model": "grok-imagine/text-to-video",
  "input": {
    "prompt": "Vertical video, 9:16 aspect ratio, exactly 10 seconds long...",
    "aspect_ratio": "9:16",
    "mode": "normal",
    "duration": 10,
    "resolution": "720p"
  }
}
```

## Formato do Retorno (`recordInfo`)
* `data.state`: `"success"`
* `data.resultJson`: Objeto ou string JSON com `resultUrls` (lista de links MP4)
* Tempo de retenção do link: 14 dias no CDN da Kie.ai.
