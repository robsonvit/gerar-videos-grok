# Conhecimento: Runway API no Kie.ai

**Última atualização:** 2026-11-09  
**Versão documentada:** Kie.ai v1 Jobs API  
**Fonte:** [Kie.ai Runway API Docs](https://docs.kie.ai) & Live API

## Visão Geral
O modelo `runway` no Kie.ai permite geração de vídeo Text-to-Video e Image-to-Video de alta fidelidade visual (Gen-4 Turbo) com custo flat inferior ao Grok Imagine.

## Custos no Kie.ai
- **720p 5s:** 12 créditos (~$0,06 USD)
- **720p 10s:** 30 créditos (~$0,15 USD) — economia de 33% em relação ao Grok 720p (45 créditos / $0,225).
- **1080p 5s:** 30 créditos (~$0,15 USD)

## Endpoint de Criação de Tarefa
- **URL:** `POST https://api.kie.ai/api/v1/jobs/createTask`
- **Headers:**
  - `Authorization: Bearer <KIE_API_KEY>`
  - `Content-Type: application/json`

## Payload para Text-to-Video 10s 720p
```json
{
  "model": "runway",
  "input": {
    "prompt": "Prompt visual detalhado em inglês...",
    "aspect_ratio": "9:16",
    "duration": 10,
    "quality": "720p",
    "watermark": ""
  }
}
```

## Polling e Resultado
- **URL:** `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<TASK_ID>`
- **Status de Sucesso:** `data.state == "success"`
- **URL do Vídeo:** `data.response.resultUrls[0]` ou `json.loads(data.resultJson)["resultUrls"][0]`
- **Áudio:** O Runway gera vídeo mudo. A narração deve ser sintetizada separadamente (via Fish Audio ou Edge-TTS) e combinada via FFmpeg.
