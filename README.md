# 🎬 Gerar Vídeos com Grok — Pipeline Automatizado

> Pipeline completo de criação de vídeos curtos (~15s) usando GitHub Actions, OpenRouter API e Grok Aurora, com envio automático para Telegram.

---

## 📋 Índice

- [Objetivo](#-objetivo)
- [Arquitetura](#-arquitetura)
- [Estrutura de Diretórios](#-estrutura-de-diretórios)
- [Dependências](#-dependências)
- [Configuração Inicial](#-configuração-inicial)
  - [1. Fork/Clone do Repositório](#1-forkclone-do-repositório)
  - [2. GitHub Secrets](#2-github-secrets)
  - [3. OpenRouter API](#3-openrouter-api)
  - [4. Telegram Bot](#4-telegram-bot)
  - [5. Cookies do Grok](#5-cookies-do-grok-autenticação)
- [Personalização](#-personalização)
- [Execução](#-execução)
- [Solução de Problemas](#-solução-de-problemas)
- [Limitações Conhecidas](#-limitações-conhecidas)
- [Segurança](#-segurança)

---

## 🎯 Objetivo

Automatizar o processo de criação de vídeos curtos (~15 segundos) no formato vertical (9:16), adequados para:
- **YouTube Shorts**
- **Instagram Reels**
- **TikTok**

O pipeline é executado inteiramente no GitHub Actions e envia o resultado final para um canal/grupo do Telegram.

---

## 🏗️ Arquitetura

```
GitHub Actions
     │
     ▼
📝 Gerar Roteiro (OpenRouter API)
     │  Usa fallback entre modelos gratuitos
     ▼
🎥 Gerar Vídeo (Grok Aurora - grok.com/imagine)
     │  Automação via Playwright (Chromium headless)
     ▼
⚙️ Processar Vídeo (FFmpeg)
     │  Normalização de áudio, H.264+AAC, formato vertical
     ▼
📱 Enviar para Telegram (Bot API)
     │  Arquivo + legenda formatada
     ▼
📊 Resumo do Pipeline
```

---

## 📁 Estrutura de Diretórios

```
📦 gerar-videos-grok/
├── .github/
│   └── workflows/
│       └── video_pipeline.yml     # Workflow principal do GitHub Actions
│
├── config/
│   ├── master_prompt.txt          # Instrução principal para o LLM gerar roteiros
│   ├── models.json                # Lista de modelos OpenRouter com prioridade
│   └── settings.json              # Configurações globais do pipeline
│
├── scripts/
│   ├── generate_script.py         # Etapa 1: Gera roteiro via OpenRouter
│   ├── generate_video.py          # Etapa 2: Gera vídeo no Grok via Playwright
│   ├── process_video.py           # Etapa 3: Processa vídeo com FFmpeg
│   ├── send_telegram.py           # Etapa 4: Envia para Telegram
│   └── export_cookies.py          # Auxiliar: Exporta cookies do Grok
│
├── output/                        # Gerado automaticamente (no .gitignore)
│   ├── scripts/                   # Roteiros JSON gerados
│   ├── videos/                    # Vídeos brutos do Grok
│   ├── processed/                 # Vídeos processados (finais)
│   ├── logs/                      # Logs das execuções
│   └── screenshots/               # Screenshots de diagnóstico
│
├── requirements.txt               # Dependências Python
├── .gitignore                     # Arquivos ignorados pelo Git
└── README.md                      # Esta documentação
```

---

## 📦 Dependências

| Dependência | Versão | Uso |
|-------------|--------|-----|
| Python | 3.11+ | Runtime dos scripts |
| requests | ≥2.31 | Chamadas às APIs |
| playwright | ≥1.40 | Automação do navegador |
| FFmpeg | Qualquer | Processamento de vídeo |

> No GitHub Actions, todas as dependências são instaladas automaticamente pelo workflow.

---

## ⚙️ Configuração Inicial

### 1. Fork/Clone do Repositório

```bash
# Clone o repositório
git clone https://github.com/SEU_USUARIO/gerar-videos-grok.git
cd gerar-videos-grok
```

### 2. GitHub Secrets

Acesse: **Repositório → Settings → Secrets and variables → Actions → New repository secret**

| Secret | Descrição | Obrigatório |
|--------|-----------|-------------|
| `OPENROUTER_API_KEY` | Chave da API do OpenRouter | ✅ Sim |
| `TELEGRAM_BOT_TOKEN` | Token do bot do Telegram | ✅ Sim |
| `TELEGRAM_CHAT_ID` | ID do chat/canal/grupo Telegram | ✅ Sim |
| `GROK_COOKIES` | Cookies de autenticação do Grok | ✅ Sim |

> **⚠️ IMPORTANTE:** Nunca coloque esses valores diretamente no código ou em arquivos que serão comittados.

### 3. OpenRouter API

1. Acesse [openrouter.ai](https://openrouter.ai)
2. Crie uma conta gratuita
3. Vá em **Keys** → **Create Key**
4. Copie a chave e adicione ao Secret `OPENROUTER_API_KEY`

Os modelos gratuitos já estão configurados em `config/models.json`. O sistema usa fallback automático se um modelo falhar.

### 4. Telegram Bot

#### Criar o Bot
1. No Telegram, abra o chat com [@BotFather](https://t.me/BotFather)
2. Envie `/newbot`
3. Siga as instruções e copie o **Token**
4. Adicione ao Secret `TELEGRAM_BOT_TOKEN`

#### Obter o Chat ID
```
Opção A - Chat pessoal:
1. Envie uma mensagem para o seu bot
2. Acesse: https://api.telegram.org/bot<TOKEN>/getUpdates
3. Copie o valor de "chat.id"

Opção B - Canal:
1. Adicione o bot ao canal como Administrador
2. O Chat ID de canais começa com -100
```
4. Adicione o ID ao Secret `TELEGRAM_CHAT_ID`

### 5. Cookies do Grok (Autenticação)

O pipeline precisa de uma sessão autenticada no Grok para gerar vídeos.

#### Método Recomendado: Extensão de Navegador

1. Instale a extensão **"Cookie-Editor"** no Chrome/Edge
2. Acesse [grok.com/imagine](https://grok.com/imagine) e **faça login com sua conta**
3. Clique no ícone da extensão Cookie-Editor
4. Clique em **"Export"** → **"Export as JSON"**
5. Copie todo o conteúdo JSON
6. Cole no GitHub Secret `GROK_COOKIES`

#### Método Alternativo: Script Local

```bash
# Instale as dependências localmente
pip install playwright
playwright install chromium

# Execute o script de exportação
python scripts/export_cookies.py
```

Siga as instruções no terminal. O arquivo `grok_cookies_PRIVADO.json` será criado localmente — copie seu conteúdo para o Secret.

> **⚠️ IMPORTANTE:**
> - Seus cookies são suas credenciais pessoais. Nunca compartilhe.
> - Os cookies **expiram** após algum tempo. Você precisará renová-los periodicamente.
> - Configure **apenas cookies da sua própria conta**.

---

## 🎨 Personalização

### Prompt Mestre (`config/master_prompt.txt`)

Edite este arquivo para definir o tipo de conteúdo que será gerado. O LLM usará esta instrução para criar cada novo roteiro.

**Exemplo — Vídeos de receitas:**
```
Crie um roteiro para um vídeo curto de 15 segundos no formato vertical sobre uma receita rápida e deliciosa. O vídeo deve ser visualmente impactante com close-ups dos ingredientes e do prato final...
```

**Exemplo — Dicas de produtividade:**
```
Crie um roteiro para um vídeo curto de 15 segundos com uma dica poderosa de produtividade ou mentalidade. Use linguagem direta, impactante e motivacional...
```

### Modelos da OpenRouter (`config/models.json`)

Edite a lista para mudar a ordem de prioridade ou adicionar novos modelos. Acesse [openrouter.ai/models](https://openrouter.ai/models) para ver os modelos disponíveis.

### Configurações Globais (`config/settings.json`)

```json
{
  "video": {
    "target_duration_seconds": 15,    // Duração alvo
    "resolution": "720p",             // Resolução
    "fps": 30                         // FPS
  },
  "generation": {
    "timeout_seconds": 300,           // Tempo máximo de espera pelo vídeo
    "max_retries": 3,                 // Tentativas por etapa
    "headless": true                  // false para ver o navegador (debug local)
  }
}
```

---

## ▶️ Execução

### Execução Manual

1. Vá em **Actions** → **🎬 Video Pipeline - Gerar Vídeo com Grok**
2. Clique em **"Run workflow"**
3. Preencha os campos opcionais:
   - **custom_prompt**: Prompt visual direto (ignora o master_prompt.txt)
   - **titulo**: Título personalizado
   - **notify_telegram**: `true` ou `false`
4. Clique em **"Run workflow"**

### Execução Agendada

Para ativar execução automática, edite `.github/workflows/video_pipeline.yml` e descomente a seção `schedule`:

```yaml
schedule:
  - cron: "0 9 * * 1,3,5"  # Segunda, Quarta e Sexta às 09h UTC
```

> Use [crontab.guru](https://crontab.guru) para criar expressões cron.

---

## 🔍 Solução de Problemas

### ❌ "OPENROUTER_API_KEY não encontrado"
→ Verifique se o Secret está configurado corretamente no repositório.

### ❌ "Campo de input não encontrado" / Vídeo não gerado
→ A interface do Grok pode ter mudado. Verifique os screenshots em `output/screenshots/` nos artefatos do workflow. Atualize os seletores em `scripts/generate_video.py`.

### ❌ "Cookies inválidos" / Não está logado no Grok
→ Os cookies expiraram. Repita o processo de exportação de cookies e atualize o Secret `GROK_COOKIES`.

### ❌ "FFmpeg falhou"
→ O vídeo baixado pode estar corrompido. Verifique os logs e o artefato `video-raw-*`.

### ❌ Arquivo muito grande para o Telegram (>50MB)
→ Reduza `video_bitrate` em `config/settings.json`. Tente `1500k` ou `1000k`.

### 📸 Screenshots de Diagnóstico
Sempre que ocorre um erro, screenshots são salvas. Baixe o artefato `screenshots-*` do workflow para ver o estado do navegador no momento do erro.

---

## ⚠️ Limitações Conhecidas

1. **Cookies do Grok expiram** — você precisará renová-los periodicamente (geralmente a cada 7-30 dias).

2. **Seletores da UI podem mudar** — se o Grok atualizar a interface, os seletores em `generate_video.py` precisarão ser atualizados. Os seletores estão claramente marcados com comentários `# SELETOR:`.

3. **Rate limits do Grok** — o Grok pode ter limites de uso. Se o pipeline falhar com frequência, aguarde antes de executar novamente.

4. **Modelos gratuitos da OpenRouter** — podem ter limites de uso. Se todos os modelos gratuitos falharem, o sistema tentará o modelo pago configurado como último fallback.

5. **Tempo de geração variável** — vídeos de IA podem levar de 1 a 5 minutos. O timeout está configurado para 5 minutos.

---

## 🔒 Segurança

- ✅ **Nenhuma credencial no código** — tudo via GitHub Secrets
- ✅ **Output ignorado pelo Git** — pasta `output/` no `.gitignore`
- ✅ **Cookies como Secret** — nunca no código ou em arquivos comittados
- ✅ **Acesso apenas à sua conta** — o script usa apenas cookies que você forneceu
- ✅ **HTTPS em todas as chamadas** — OpenRouter, Telegram e Grok

---

## 📊 Fluxo de Dados

```
master_prompt.txt → OpenRouter API → roteiro.json
                                          │
                                    prompt_visual
                                          │
                                    grok.com/imagine
                                          │
                                    video_raw.mp4
                                          │
                                      FFmpeg
                                          │
                                   processed.mp4
                                          │
                                   Telegram Bot API
                                          │
                                    📱 Seu Chat
```

---

*Desenvolvido com GitHub Actions, OpenRouter, Playwright e FFmpeg.*
