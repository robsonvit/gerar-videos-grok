# Conhecimento: Fish Audio API (TTS)

**Última atualização:** 2026-11-09  
**Versão documentada:** v1  
**Fonte:** [Fish Audio API Documentation](https://fish.audio/app/developers) & Implementação Projeto CRIAÇÃO VÍDEOS JESUS

## Visão Geral
O Fish Audio oferece síntese de voz neural e clonagem de voz via API. Para desenvolvedores, o modelo `s2.1-pro-free` é gratuito para testes e chamadas moderadas.

## Endpoint e Autenticação
- **URL:** `POST https://api.fish.audio/v1/tts`
- **Headers Obrigatórios:**
  - `Authorization: Bearer <FISH_API_KEY>`
  - `Content-Type: application/json`
  - `model: s2.1-pro-free` (⚠️ **CRUCIAL**: O modelo deve ser passado no header para ativar o plano gratuito).

## Payload (JSON)
```json
{
  "text": "Texto a ser narrado em português...",
  "reference_id": "<VOICE_ID>",
  "format": "mp3",
  "mp3_bitrate": 192,
  "normalize": true,
  "latency": "normal"
}
```

## Parâmetros Críticos
- `text`: Texto para síntese.
- `reference_id`: ID da voz clonada ou escolhida no catálogo do Fish Audio.
- `format`: Formato de saída (`mp3` ou `wav`).
- `normalize`: Normalização de áudio ativada por padrão (`true`).

## Tratamento de Erros e Fallback
- `402 Insufficient Credit`: Saldo de API esgotado.
- `429 Rate Limit`: Muitas requisições em curto espaço de tempo.
- **Boa Prática:** Implementar fallback automático para `edge-tts` (Microsoft, gratuito sem token) caso a API do Fish Audio esteja indisponível.
