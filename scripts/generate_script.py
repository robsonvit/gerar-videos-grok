#!/usr/bin/env python3
"""
generate_script.py
Gera o roteiro do vídeo utilizando a OpenRouter API com fallback entre modelos.
"""

import json
import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
import requests

# Configuração de encoding para suportar caracteres especiais e emojis em qualquer OS
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


def load_config(base_dir: Path) -> tuple[dict, list, str]:
    """Carrega as configurações do projeto."""
    settings_path = base_dir / "config" / "settings.json"
    models_path = base_dir / "config" / "models.json"
    master_prompt_path = base_dir / "config" / "master_prompt.txt"

    if not settings_path.exists():
        logger.error(f"Arquivo de configuração não encontrado: {settings_path}")
        sys.exit(1)

    if not models_path.exists():
        logger.error(f"Arquivo de modelos não encontrado: {models_path}")
        sys.exit(1)

    if not master_prompt_path.exists():
        logger.error(f"Prompt mestre não encontrado: {master_prompt_path}")
        sys.exit(1)

    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    with open(models_path, "r", encoding="utf-8") as f:
        models_data = json.load(f)
        models = models_data.get("models", [])

    with open(master_prompt_path, "r", encoding="utf-8") as f:
        master_prompt = f.read().strip()

    return settings, models, master_prompt


def call_openrouter(
    api_key: str,
    model_id: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
    base_url: str,
    timeout: int
) -> tuple[str | None, bool]:
    """
    Faz uma chamada à OpenRouter API e retorna (conteúdo, deve_tentar_novamente).
    Se o erro for não-recuperável (400, 401, 403, 404), deve_tentar_novamente=False.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/gerar-videos-grok",
        "X-Title": "Gerar Videos Grok Pipeline"
    }

    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    try:
        logger.info(f"Chamando modelo: {model_id}")
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout
        )

        if response.status_code == 200:
            data = response.json()
            choices = data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                # Apenas extrai o conteúdo final do modelo (nunca reasoning/scratchpad interno)
                content = msg.get("content") or msg.get("text") or ""
                if isinstance(content, str) and content.strip():
                    logger.info(f"Resposta recebida com sucesso do modelo {model_id}")
                    return content.strip(), False
            logger.warning(f"Modelo {model_id} retornou 200 mas sem conteúdo de texto válido: {str(data)[:200]}")
            return None, True

        elif response.status_code in (400, 401, 403, 404):
            logger.warning(
                f"Modelo {model_id} retornou erro permanente ({response.status_code}): {response.text[:200]}"
            )
            return None, False

        else:
            logger.warning(
                f"Modelo {model_id} retornou status transitório {response.status_code}: {response.text[:200]}"
            )
            return None, True

    except requests.exceptions.Timeout:
        logger.warning(f"Timeout ({timeout}s) ao chamar modelo {model_id}")
        return None, True
    except requests.exceptions.ConnectionError as e:
        logger.warning(f"Erro de conexão com modelo {model_id}: {e}")
        return None, True
    except Exception as e:
        logger.warning(f"Erro inesperado ao chamar modelo {model_id}: {e}")
        return None, True


def parse_structured_response(content: str, tema_sugerido: str = "") -> dict | None:
    """
    Parseia a resposta estruturada do master prompt.
    Extrai blocos de PROMPT VISUAL (ENGLISH) e NARRAÇÃO (PORTUGUÊS BRASILEIRO).
    Se houver múltiplos blocos, seleciona um bloco exclusivo com narração limpa.
    """
    import re
    import random

    # Procura por blocos completos: PROMPT VISUAL seguido de NARRAÇÃO
    blocos = []
    
    # Divide por blocos de PROMPT VISUAL
    partes = re.split(r'(?i)PROMPT\s+VISUAL(?:\s*\([^\)]*\))?\s*:\s*', content)
    for p in partes:
        if not p.strip():
            continue
        # Dentro de cada parte, procura pela NARRAÇÃO
        match_narr = re.split(r'(?i)NARRAÇÃO(?:\s*\([^\)]*\))?\s*:\s*', p, maxsplit=1)
        if len(match_narr) == 2:
            prompt_vis = match_narr[0].strip()
            # A narração vai até o próximo delimitador de bloco ou fim
            narr_text = match_narr[1].strip()
            # Limpa se houver início de outro bloco ou instrução
            narr_text = re.split(r'(?i)(?:\n\s*PROMPT\s+VISUAL|\n\s*###|\n\s*\*\*PROMPT|\Z)', narr_text)[0].strip()
            # Remove delimitadores Markdown (---, ***, ===, etc.) e aspas residuais
            narr_text = re.sub(r'[\r\n\s]*(?:---+|\*\*\*+|===+|___+)[\r\n\s]*$', '', narr_text).strip()
            narr_text = re.sub(r'^[\r\n\s]*(?:---+|\*\*\*+|===+|___+)[\r\n\s]*', '', narr_text).strip().strip('"\'')
            prompt_vis = re.sub(r'[\r\n\s]*(?:---+|\*\*\*+|===+|___+)[\r\n\s]*$', '', prompt_vis).strip().strip('"\'')
            if prompt_vis and narr_text:
                blocos.append((prompt_vis, narr_text))

    if blocos:
        # Escolhe aleatoriamente um dos blocos gerados para garantir variedade máxima
        prompt_grok, gancho = random.choice(blocos)
    else:
        # Fallback genérico caso o formato venha ligeiramente diferente
        m_vis = re.search(r'(?i)PROMPT\s+VISUAL[^\n:]*:\s*(.*?)(?=\n\s*NARRAÇÃO|\Z)', content, re.DOTALL)
        prompt_grok = m_vis.group(1).strip() if m_vis else content.strip()
        
        m_narr = re.search(r'(?i)NARRAÇÃO[^\n:]*:\s*(.*?)(?=\n\s*PROMPT|\Z)', content, re.DOTALL)
        gancho = m_narr.group(1).strip() if m_narr else "Vídeo gerado automaticamente"

        # Limpa delimitadores residuais de markdown
        prompt_grok = re.sub(r'[\r\n\s]*(?:---+|\*\*\*+|===+|___+)[\r\n\s]*$', '', prompt_grok).strip().strip('"\'')
        gancho = re.sub(r'[\r\n\s]*(?:---+|\*\*\*+|===+|___+)[\r\n\s]*$', '', gancho).strip().strip('"\'')

    # Tenta extrair o nome da receita da narração
    # Padrão: 'vai fazer um(a) [delicioso(a)] [nome da receita], rápido...'
    titulo = ""
    match_titulo = re.search(r'vai\s+fazer\s+um[a]?\s+(?:delicios[oa]\s+)?([^,?.!]+)', gancho, re.IGNORECASE)
    if match_titulo:
        titulo = match_titulo.group(1).strip().title()
    elif tema_sugerido:
        titulo = tema_sugerido.title()
    else:
        titulo = "Receita Deliciosa"

    logger.info(f"Receita identificada: '{titulo}'")
    logger.info(f"Tamanho do prompt visual: {len(prompt_grok)} chars")
    logger.info(f"Narração extraída ({len(gancho)} chars): {gancho[:120]}...")

    return {
        "titulo": titulo,
        "prompt_visual": prompt_grok,
        "narracao": gancho,
        "legenda": "",
        "hashtags": "",
        "conceito": titulo,
        "gancho": gancho,
    }


RECEITAS_DB = {
    "Bolo de Cenoura com Cobertura de Chocolate Vulcão": (
        "Você sabia que se misturar 3 cenouras, 3 ovos, meia xícara de óleo e 2 xícaras de farinha, vai fazer um bolo de cenoura vulcão irresistível? Bata tudo no liquidificador, asse por 40 minutos e despeje essa calda quente de chocolate super cremosa!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. First-person POV cooking in a cozy Brazilian home kitchen. 0-4s Beginning: fresh sliced carrots, eggs, and golden oil blended into smooth orange batter. 4-10s Middle: pouring batter into a bundt pan and baking until golden fluffy. 10-15s End: pouring hot glossy chocolate fudge over the cake and cutting a steaming slice, delicious texture. 4k food videography, no text."
    ),
    "Pudim de Leite Condensado com Calda Dourada": (
        "Você sabia que se misturar 1 lata de leite condensado, a mesma medida de leite e 3 ovos inteiros, vai fazer um pudim de leite lisinho e maravilhoso? É só bater, despejar na forma caramelizada, assar em banho-maria e desenformar bem geladinho!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV cooking in a cozy Brazilian kitchen. 0-4s Beginning: pouring condensed milk, whole milk, and eggs into a blender bowl. 4-10s Middle: pouring the smooth mixture into a caramelized golden ring mold and baking in water bath. 10-15s End: flipping the chilled silky pudim onto a glass platter, golden caramel cascading down. 4k food videography, no text."
    ),
    "Torta Cremosa de Frango de Liquidificador": (
        "Você sabia que se misturar 3 ovos, 2 xícaras de leite, meia de óleo e 2 de farinha, vai fazer uma torta de frango de liquidificador super cremosa? Despeje metade da massa, adicione o frango desfiado com requeijão, cubra e asse até dourar!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV in a Brazilian kitchen. 0-4s Beginning: blending eggs, milk, oil, and flour in a blender. 4-10s Middle: pouring half the batter into baking dish, layering juicy shredded chicken with creamy catupiry, topping with remaining batter. 10-15s End: cutting a steaming golden square of pie, melted cheese stretching, appetizing presentation. 4k, no text."
    ),
    "Pão de Queijo Mineiro Super Recheado": (
        "Você sabia que se misturar 500g de polvilho, 1 xícara de leite quente, 2 ovos e 200g de queijo minas curado, vai fazer um pão de queijo quentinho e crocante? Misture a massa, modele as bolinhas e asse até ficarem douradas!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV in a rustic Brazilian kitchen. 0-4s Beginning: hands mixing tapioca starch, warm milk, and grated Minas cheese in a clay bowl. 4-10s Middle: rolling smooth dough balls onto baking sheet and baking in oven. 10-15s End: breaking open a steaming golden cheese bread, soft stretchy cheese interior. 4k, no text."
    ),
    "Mousse Aerada de Maracujá com Polpa Fresca": (
        "Você sabia que se misturar 1 lata de leite condensado, 1 caixa de creme de leite e 1 xícara de suco concentrado de maracujá, vai fazer uma mousse aerada divina? Bata por 3 minutos, leve à geladeira e finalize com a polpa fresca por cima!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV in a bright Brazilian kitchen. 0-4s Beginning: pouring condensed milk, table cream, and yellow passion fruit juice into a blender. 4-10s Middle: blending into a thick velvety mousse and pouring into crystal dessert glasses. 10-15s End: spooning fresh passion fruit seeds on top and dipping a spoon into the airy texture. 4k, no text."
    ),
    "Bolo de Milho Cremoso Caipira": (
        "Você sabia que se misturar 1 lata de milho verde, 1 lata de leite condensado, 3 ovos e meia xícara de fubá, vai fazer um bolo de milho caipira cremosíssimo? Bata no liquidificador, asse por 40 minutos e sirva quentinho com aquele café fresco!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV in a warm Brazilian country kitchen. 0-4s Beginning: sweet corn, condensed milk, eggs, and cornmeal going into blender. 4-10s Middle: pouring yellow batter into cake pan and baking until tops are golden. 10-15s End: cutting a slice showing the creamy custard-like center, steam rising, cozy lighting. 4k, no text."
    ),
    "Brigadeiro Gourmet Macio com Granulado de Chocolate": (
        "Você sabia que se misturar 1 lata de leite condensado, 1 colher de manteiga e 4 colheres de cacau em pó, vai fazer um brigadeiro gourmet super macio? Mexa em fogo baixo até desgrudar da panela, enrole e passe no granulado nobre!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV in cozy kitchen. 0-4s Beginning: wooden spoon stirring condensed milk, butter, and rich cocoa in an enameled pan. 4-10s Middle: cooking until glossy and pulling away from bottom, cooling on a plate. 10-15s End: buttered hands rolling shiny balls in chocolate sprinkles and placing in paper cups. 4k, no text."
    ),
    "Escondidinho de Carne Seca com Purê de Mandioca": (
        "Você sabia que se misturar 1kg de mandioca cozida com manteiga e leite para o purê, vai fazer um escondidinho de carne seca sensacional? Monte camadas alternando o purê e a carne seca refogada, cubra com queijo e gratine no forno!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV cooking. 0-4s Beginning: mashing steamed cassava with butter and milk into silky puree. 4-10s Middle: assembling baking dish with shredded seasoned beef, topped with cassava puree and mozzarella. 10-15s End: taking bubbling golden gratin from oven and scooping a hearty steaming portion onto plate. 4k, no text."
    ),
    "Pastel de Feira Crocante com Recheio Generoso": (
        "Você sabia que se misturar 500g de farinha de trigo, água morna, sal e uma dose de cachaça, vai fazer uma massa de pastel de feira super crocante? Abra bem fininha, recheie com carne moída temperada e frite no óleo bem quente!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV cooking. 0-4s Beginning: kneading smooth pastel dough on floured wooden board. 4-10s Middle: rolling dough paper-thin, filling with seasoned minced beef, crimping edges with fork. 10-15s End: frying in bubbling hot oil until blistered crispy gold, breaking in half showing juicy steaming meat. 4k, no text."
    ),
    "Pavê Tradicional de Chocolate com Creme de Baunilha": (
        "Você sabia que se misturar leite condensado, gemas e leite para o creme branco, vai fazer um pavê tradicional irresistível? Intercale camadas de biscoito champanhe umedecido no leite com o creme de baunilha e cubra com ganache de chocolate meio amargo!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV dessert prep. 0-4s Beginning: stirring vanilla custard in a saucepan until creamy thick. 4-10s Middle: dipping ladyfinger biscuits in milk, layering in glass dish with custard. 10-15s End: spreading glossy dark chocolate ganache on top, scooping a multi-layered slice onto dessert plate. 4k, no text."
    ),
    "Empadão Especial de Frango com Requeijão": (
        "Você sabia que se misturar 400g de farinha de trigo com 200g de manteiga gelada, vai fazer uma massa podre de empadão que derrete na boca? Recheie com frango desfiado suculento e bastante requeijão cremoso antes de assar até dourar!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV baking. 0-4s Beginning: fingertips blending cold butter into flour creating flaky crumbly pastry dough. 4-10s Middle: lining pie dish with pastry, packing with creamy shredded chicken and requeijao, sealing with lattice crust. 10-15s End: slicing a golden baked pie, flaky crust crumbling, creamy chicken filling steaming. 4k, no text."
    ),
    "Bolo de Chocolate Fofinho com Calda Quente": (
        "Você sabia que se misturar 3 ovos, 1 xícara de açúcar, 1 de cacau e 2 de farinha, vai fazer um bolo de chocolate fofíssimo? Misture tudo com carinho, asse até crescer e cubra com uma calda quente de chocolate brilhante e aveludada!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV baking. 0-4s Beginning: whisking eggs, sugar, melted butter and dark cocoa in ceramic bowl. 4-10s Middle: folding in flour, pouring dark batter into pan, baking until tall and springy. 10-15s End: pouring steaming hot chocolate sauce over cake, cutting a rich tender slice onto plate. 4k, no text."
    ),
    "Quindim Brilhante e Amarelinho de Padaria": (
        "Você sabia que se misturar 10 gemas peneiradas, 200g de açúcar e 100g de coco ralado úmido, vai fazer um quindim amarelinho de padaria? Misture delicadamente, unte a forma com manteiga e açúcar, e asse em banho-maria até dourar!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV sweet making. 0-4s Beginning: passing egg yolks through fine sieve into bowl with grated coconut and sugar. 4-10s Middle: pouring bright yellow mixture into buttered sugared molds, baking in water bath. 10-15s End: unmolding glossy translucent golden quindim with toasted coconut base onto white porcelain. 4k, no text."
    ),
    "Torta de Limão Fácil com Merengue Tostado": (
        "Você sabia que se misturar biscoito triturado com manteiga para a base e leite condensado com suco de limão para o recheio, vai fazer uma torta de limão espetacular? Coloque o recheio na massa assada, cubra com merengue e toste com maçarico!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV pastry. 0-4s Beginning: pressing buttery crushed biscuit crumbs into tart pan. 4-10s Middle: whisking condensed milk with lime juice until naturally thick, pouring over crust. 10-15s End: piping fluffy white meringue peaks on top, blowtorch toasting them golden brown, serving slice. 4k, no text."
    ),
    "Coxinha de Frango com Massa de Batata e Catupiry": (
        "Você sabia que se misturar caldo de frango, batata cozida amassada e farinha de trigo, vai fazer uma massa de coxinha macia e saborosa? Modele com recheio generoso de frango com catupiry, empane e frite até ficar crocante e dourada!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV cooking. 0-4s Beginning: cooking potato dough in saucepan until silky smooth. 4-10s Middle: shaping dough tear-drops filled with shredded spiced chicken and catupiry, dipping in breadcrumbs. 10-15s End: frying in deep hot oil until crunchy amber, breaking open showing steaming molten chicken center. 4k, no text."
    ),
    "Rocambole de Doce de Leite Macio": (
        "Você sabia que se misturar 4 ovos, 4 colheres de açúcar e 4 de farinha de trigo, vai fazer uma massa de rocambole super fofa? Asse em assadeira rasa por 15 minutos, espalhe doce de leite cremoso, enrole ainda morno e polvilhe açúcar!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV baking. 0-4s Beginning: whipping eggs and sugar into pale fluffy ribbon stage. 4-10s Middle: gently folding flour, spreading thinly on parchment sheet, baking light golden. 10-15s End: spreading dark caramel doce de leite, tightly rolling with kitchen towel, slicing thick swirls. 4k, no text."
    ),
    "Panqueca de Carne Moída com Molho Vermelho e Queijo": (
        "Você sabia que se misturar 1 xícara de leite, 1 ovo, 1 xícara de farinha e uma pitada de sal, vai fazer discos de panqueca perfeitamente fininhos? Recheie com carne moída bem temperada, enrole, cubra com molho de tomate e gratine com queijo!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV cooking. 0-4s Beginning: whisking crepe batter and swirling thin layer into buttered skillet. 4-10s Middle: spooning rich seasoned ground beef onto crepes, rolling tightly into baking dish. 10-15s End: spooning bubbling tomato sauce and melted mozzarella, lifting a hot saucy pancake onto plate. 4k, no text."
    ),
    "Cocada Cremosa de Colher": (
        "Você sabia que se misturar 1 coco fresco ralado, 1 lata de leite condensado e 1 xícara de leite, vai fazer uma cocada cremosa de colher de lamber os dedos? Cozinhe em fogo baixo mexendo sempre até engrossar e sirva cremosa na taça!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV sweet prep. 0-4s Beginning: fresh shredded coconut, condensed milk and milk poured into heavy pan. 4-10s Middle: wooden spoon stirring bubbling white coconut cream over low heat until thickened. 10-15s End: spooning warm glistening cocada into glass bowls, dipping spoon showing rich creamy texture. 4k, no text."
    ),
    "Sonho Recheado com Creme de Confeiteiro": (
        "Você sabia que se misturar farinha, fermento biológico, leite morno e ovos, vai fazer uma massa de sonho leve como nuvem? Modele as bolinhas, deixe fermentar, frite em fogo médio e recheie com bastante creme de confeiteiro aveludado e quentinho!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV bakery. 0-4s Beginning: kneading sweet enriched yeast dough on wooden board. 4-10s Middle: rising round dough puffs, gently lowering into golden oil until puffy brown. 10-15s End: slicing warm doughnut, piping thick yellow vanilla pastry cream, dusting powdered sugar. 4k, no text."
    ),
    "Bolo de Fubá Cremoso com Queijo": (
        "Você sabia que se misturar 3 ovos, 3 xícaras de leite, 1 de fubá e 1 xícara de queijo parmesão ralado, vai fazer um bolo de fubá cremoso dos deuses? Bata tudo no liquidificador e asse até formar aquela camada cremosa no meio!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV baking. 0-4s Beginning: pouring eggs, milk, cornmeal, and grated parmesan cheese into glass blender. 4-10s Middle: blending liquid batter, pouring into greased pan, baking until golden top. 10-15s End: cutting warm slice showing firm cake top, creamy custardy cheese layer in center, steam rising. 4k, no text."
    ),
    "Mousse de Limão Rápida com Raspas": (
        "Você sabia que se misturar 1 lata de leite condensado, 1 caixinha de creme de leite e meia xícara de suco de limão taiti, vai fazer uma mousse refrescante e rápida? Bata por 2 minutos, distribua em taças e decore com raspas de limão!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV dessert. 0-4s Beginning: pouring condensed milk, cream, and freshly squeezed green lime juice in blender. 4-10s Middle: blending into thick silky lime cream, pouring into clear glasses. 10-15s End: grating fresh lime zest over dessert, dipping spoon into chilled thick velvety mousse. 4k, no text."
    ),
    "Bolo de Laranja Molhadinho e Fofinho": (
        "Você sabia que se misturar 3 ovos, 1 xícara de suco natural de laranja, meia de óleo e 2 de farinha, vai fazer um bolo de laranja molhadinho e fofinho? Asse por 35 minutos, regue com calda morna de laranja e sirva ainda quentinho!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV baking. 0-4s Beginning: blending whole seedless oranges, eggs, sugar, and oil into fragrant batter. 4-10s Middle: folding flour, pouring into ring pan, baking golden brown. 10-15s End: pouring hot orange glaze over warm cake, cutting moist fragrant slice, juice glistening. 4k, no text."
    ),
    "Enroladinho de Salsicha e Queijo Assado": (
        "Você sabia que se misturar 2 xícaras de farinha, 1 de leite morno, fermento e uma colher de manteiga, vai fazer enroladinhos assados perfeitos? Enrole a massa na salsicha com queijo fatiado, pincele gema e asse até ficar bem douradinho!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV baking. 0-4s Beginning: kneading soft bread dough on wooden surface. 4-10s Middle: wrapping thin strips of dough around sausage and melted cheese, brushing with egg yolk and oregano. 10-15s End: taking baking sheet from oven, pulling apart hot golden bun, melted cheese stretching. 4k, no text."
    ),
    "Torta Holandesa com Creme de Baunilha e Chocolate": (
        "Você sabia que se misturar manteiga, açúcar e creme de leite para o recheio sobre base de biscoito, vai fazer uma torta holandesa digna de confeitaria? Forre a lateral com biscoitos calipso, preencha com o creme e finalize com ganache brilhante!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV pastry. 0-4s Beginning: lining ring mold with chocolate covered round biscuits and crumb base. 4-10s Middle: pouring fluffy white vanilla cream into center, smoothing flat. 10-15s End: pouring dark chocolate ganache mirror glaze, cutting chilled slice showing crisp biscuit border. 4k, no text."
    ),
    "Feijão Tropeiro Mineiro Completo": (
        "Você sabia que se misturar 500g de feijão al dente, bacon crocante, linguiça calabresa, ovos mexidos e farinha de mandioca, vai fazer um feijão tropeiro mineiro autêntico? Refogue tudo com alho na gordura do bacon, adicione couve fatiada e sirva com torresmo bem sequinho!",
        "Vertical video, 9:16 aspect ratio, exactly 15 seconds long. POV cooking. 0-4s Beginning: sizzling diced bacon and sliced calabresa sausage in iron skillet. 4-10s Middle: tossing cooked beans, scrambled eggs, garlic, and manioc flour into skillet with shredded collard greens. 10-15s End: scooping generous steaming spoonful of tropeiro onto rustic plate, topping with crispy torresmo cracklings. 4k, no text."
    ),
}

RECEITAS_VARIADAS = list(RECEITAS_DB.keys())


def validate_script(content: str, settings: dict, tema_sugerido: str = "") -> dict | None:
    """Valida e parseia o roteiro gerado com exigência estrita de narração culinária."""
    import re
    script_config = settings.get("script", {})
    min_len = script_config.get("min_length_chars", 50)
    max_len = script_config.get("max_length_chars", 2500)
    validate_json = script_config.get("validate_json", True)

    if not content:
        logger.error("Conteúdo do roteiro está vazio")
        return None

    script_data = None

    # Tenta parsear como JSON
    if validate_json:
        content_clean = content.strip()
        if "```json" in content_clean:
            start = content_clean.find("```json") + 7
            end = content_clean.find("```", start)
            content_clean = content_clean[start:end].strip() if end != -1 else content_clean[start:].strip()
        elif "```" in content_clean:
            start = content_clean.find("```") + 3
            end = content_clean.find("```", start)
            content_clean = content_clean[start:end].strip() if end != -1 else content_clean[start:].strip()

        try:
            parsed = json.loads(content_clean)
            if isinstance(parsed, dict) and "prompt_visual" in parsed and "narracao" in parsed:
                script_data = parsed
                logger.info(f"Roteiro em formato JSON válido: '{script_data.get('titulo')}'")
        except Exception:
            pass

    if not script_data:
        script_data = parse_structured_response(content, tema_sugerido)
        if not script_data:
            logger.error("Falha ao parsear resposta.")
            return None

    # Validação obrigatória da NARRAÇÃO
    narracao = script_data.get("narracao", "").strip()
    if not narracao or "gerado automaticamente" in narracao.lower():
        logger.warning("Roteiro rejeitado: narração ausente ou placeholder genérico.")
        return None

    palavras_narracao = narracao.split()
    if len(palavras_narracao) < 25:
        logger.warning(f"Roteiro rejeitado: narração muito curta ({len(palavras_narracao)} palavras).")
        return None

    if not re.search(r'(?i)voc[êe]\s+sabia\s+que\s+se\s+misturar', narracao):
        logger.warning("Roteiro rejeitado: narração não começa com 'Você sabia que se misturar...'.")
        return None

    # Valida tamanho do prompt visual
    prompt_visual = script_data.get("prompt_visual", "")
    if len(prompt_visual) < min_len:
        logger.error(f"Prompt visual muito curto: {len(prompt_visual)} chars (mínimo: {min_len})")
        return None

    if len(prompt_visual) > max_len:
        logger.warning(f"Prompt visual muito longo ({len(prompt_visual)} chars), truncando para {max_len}")
        script_data["prompt_visual"] = prompt_visual[:max_len]

    logger.info(f"Roteiro validado com sucesso: '{script_data.get('titulo', 'Sem título')}' ({len(palavras_narracao)} palavras na narração)")
    return script_data


def save_script(script_data: dict, output_dir: Path) -> Path:
    """Salva o roteiro gerado em arquivo JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"script_{timestamp}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)

    logger.info(f"Roteiro salvo em: {output_path}")
    return output_path


def generate_offline_recipe(tema: str) -> dict:
    """
    Gera um roteiro local com passo a passo gastronômico autêntico da receita.
    Garante 100% de conformidade com ingredientes reais, modo de preparo e narração PT-BR de 35 a 45 palavras.
    """
    tema_clean = tema.strip()

    # Busca no banco de receitas completas
    if tema_clean in RECEITAS_DB:
        narracao, prompt_visual = RECEITAS_DB[tema_clean]
    else:
        # Fallback genérico de alta fidelidade
        prompt_visual = (
            f"Vertical video, 9:16 aspect ratio, exactly 15 seconds long. "
            f"First-person POV cooking in a cozy realistic Brazilian home kitchen. "
            f"0-4s Beginning: natural hands mixing fresh authentic ingredients for {tema_clean} in a bowl with a wooden spoon. "
            f"4-10s Middle: fast dynamic preparation of {tema_clean}, cooking to golden perfection with gentle steam rising. "
            f"10-15s End: hands cutting and serving a generous steaming portion of the finished {tema_clean} on a plate. "
            f"4k food videography, no text, no subtitles."
        )
        narracao = (
            f"Você sabia que se misturar os ingredientes frescos da sua cozinha, "
            f"vai fazer um delicioso {tema_clean}, super rápido e muito prático? "
            f"Bata tudo com carinho, leve para cozinhar até dourar e sirva quentinho com aquela textura irresistível!"
        )

    logger.info(f"Roteiro com passo a passo gerado para: '{tema_clean}' ({len(narracao.split())} palavras)")
    return {
        "titulo": tema_clean,
        "prompt_visual": prompt_visual,
        "narracao": narracao,
        "legenda": "",
        "hashtags": "",
        "conceito": tema_clean,
        "gancho": narracao,
        "_meta": {
            "model_used": "offline-recipe-database",
            "model_name": "Banco Gastronômico Resiliente",
            "generated_at": datetime.now().isoformat(),
            "tema_sorteado": tema_clean,
        }
    }


def generate_script_with_fallback(
    api_key: str,
    models: list,
    master_prompt: str,
    settings: dict,
    custom_prompt: str = "",
    custom_titulo: str = ""
) -> dict:
    """Tenta gerar o roteiro usando os modelos em ordem de prioridade com fallback inteligente."""
    import random
    
    # Se houver custom_prompt fornecido manualmente via GitHub Actions
    if custom_prompt:
        titulo = custom_titulo or "Receita Personalizada"
        logger.info(f"Usando prompt personalizado manual: '{titulo}'")
        return {
            "titulo": titulo,
            "prompt_visual": custom_prompt,
            "narracao": "Você sabia que se misturar os ingredientes certos com muito carinho, vai fazer uma receita deliciosa, rápida, prática e muito gostosa?",
            "legenda": "",
            "hashtags": "",
            "conceito": titulo,
            "gancho": "",
            "_meta": {
                "model_used": "manual-custom-prompt",
                "model_name": "Custom Input",
                "generated_at": datetime.now().isoformat(),
            }
        }

    # Sorteia uma receita brasileira para garantir variedade total em cada execução
    tema_sorteado = custom_titulo or random.choice(RECEITAS_VARIADAS)
    logger.info(f"🎯 Tema sorteado para esta execução: '{tema_sorteado}'")

    # Prompt direto exigindo estritamente JSON sem pensamentos internos soltos
    prompt_com_tema = (
        f"Atue como especialista em roteiros gastronômicos para vídeos virais de 15 segundos no Grok Imagine.\n"
        f"Crie o roteiro completo para a receita brasileira: \"{tema_sorteado}\".\n\n"
        f"Responda EXCLUSIVAMENTE com um JSON válido com esta estrutura exata:\n"
        f"{{\n"
        f"  \"titulo\": \"{tema_sorteado}\",\n"
        f"  \"prompt_visual\": \"Vertical video, 9:16 aspect ratio, exactly 15 seconds long. First-person POV cooking in a cozy Brazilian kitchen. 0-4s Beginning: natural hands mixing [ingredients with visual hook]. 4-10s Middle: fast dynamic preparation of {tema_sorteado}, cooking/baking with steam rising. 10-15s End: hands cutting and serving an appetizing slice on a plate, highlighting mouth-watering texture. 4k food videography, no text, no subtitles.\",\n"
        f"  \"narracao\": \"Você sabia que se misturar [ingredientes e quantidades exatas], vai fazer um(a) delicioso(a) {tema_sorteado}? [passo a passo resumido de preparo: bater, misturar, assar ou cozinhar] e servir [finalização bem apetitosa]!\"\n"
        f"}}\n\n"
        f"REGRAS OBRIGATÓRIAS:\n"
        f"1. A narração DEVE ter entre 35 e 45 palavras no total em português brasileiro.\n"
        f"2. A narração DEVE começar obrigatoriamente com 'Você sabia que se misturar...'\n"
        f"3. A narração DEVE conter o passo a passo da receita (ingredientes com medidas, modo de fazer e servir).\n"
        f"4. O prompt_visual DEVE ser em inglês, descrevendo começo misturando (0-4s), meio preparando (4-10s) e fim servindo (10-15s).\n"
        f"5. NÃO escreva explicações, introduções ou notas. Retorne APENAS o JSON puro."
    )

    or_config = settings.get("openrouter", {})
    base_url = or_config.get("base_url", "https://openrouter.ai/api/v1")
    timeout = or_config.get("timeout_seconds", 30)
    max_retries = or_config.get("max_retries", 2)
    retry_delay = or_config.get("retry_delay_seconds", 5)

    if api_key:
        for model in models:
            model_id = model.get("id")
            max_tokens = model.get("max_tokens", 1024)
            temperature = model.get("temperature", 0.5)
            model_name = model.get("name", model_id)

            logger.info(f"Tentando modelo: {model_name}")

            for attempt in range(1, max_retries + 1):
                if attempt > 1:
                    logger.info(f"Tentativa {attempt}/{max_retries} para {model_name}")
                    time.sleep(retry_delay)

                content, should_retry = call_openrouter(
                    api_key=api_key,
                    model_id=model_id,
                    prompt=prompt_com_tema,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    base_url=base_url,
                    timeout=timeout
                )

                if content:
                    script_data = validate_script(content, settings, tema_sorteado)
                    if script_data:
                        script_data["_meta"] = {
                            "model_used": model_id,
                            "model_name": model_name,
                            "generated_at": datetime.now().isoformat(),
                            "attempt": attempt,
                            "tema_sorteado": tema_sorteado
                        }
                        return script_data
                    else:
                        logger.warning(f"Roteiro inválido do modelo {model_name}, tentando novamente...")

                if not should_retry:
                    logger.info(f"Pulando tentativas adicionais para {model_name} devido a erro definitivo.")
                    break

            logger.warning(f"Modelo {model_name} falhou após tentativas. Passando para o próximo.")
    else:
        logger.warning("Nenhuma OPENROUTER_API_KEY fornecida.")

    logger.warning(
        f"⚠️ Modelos remotos do OpenRouter indisponíveis ou geraram respostas inválidas. "
        f"Ativando gerador culinário com passo a passo autêntico para: '{tema_sorteado}'..."
    )
    return generate_offline_recipe(tema_sorteado)

    if api_key:
        for model in models:
            model_id = model.get("id")
            max_tokens = model.get("max_tokens", 1024)
            temperature = model.get("temperature", 0.7)
            model_name = model.get("name", model_id)

            logger.info(f"Tentando modelo: {model_name}")

            for attempt in range(1, max_retries + 1):
                if attempt > 1:
                    logger.info(f"Tentativa {attempt}/{max_retries} para {model_name}")
                    time.sleep(retry_delay)

                content, should_retry = call_openrouter(
                    api_key=api_key,
                    model_id=model_id,
                    prompt=prompt_com_tema,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    base_url=base_url,
                    timeout=timeout
                )

                if content:
                    script_data = validate_script(content, settings, tema_sorteado)
                    if script_data:
                        script_data["_meta"] = {
                            "model_used": model_id,
                            "model_name": model_name,
                            "generated_at": datetime.now().isoformat(),
                            "attempt": attempt,
                            "tema_sorteado": tema_sorteado
                        }
                        return script_data
                    else:
                        logger.warning(f"Roteiro inválido do modelo {model_name}, tentando novamente...")

                if not should_retry:
                    logger.info(f"Pulando tentativas adicionais para {model_name} devido a erro definitivo.")
                    break

            logger.warning(f"Modelo {model_name} falhou após tentativas. Passando para o próximo.")
    else:
        logger.warning("Nenhuma OPENROUTER_API_KEY fornecida.")

    logger.warning(
        f"⚠️ Não foi possível obter resposta dos modelos remotos do OpenRouter. "
        f"Ativando gerador local resiliente para a receita: '{tema_sorteado}'..."
    )
    return generate_offline_recipe(tema_sorteado)


def main():
    """Função principal."""
    base_dir = Path(__file__).parent.parent

    # Verifica variáveis de ambiente
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    custom_prompt = os.environ.get("CUSTOM_PROMPT", "").strip()
    custom_titulo = os.environ.get("CUSTOM_TITULO", "").strip()

    logger.info("=== INICIANDO GERAÇÃO DE ROTEIRO ===")

    # Carrega configurações
    settings, models, master_prompt = load_config(base_dir)
    logger.info(f"Modelos disponíveis: {len(models)}")
    logger.info(f"Prompt mestre carregado ({len(master_prompt)} chars)")

    # Gera roteiro com fallback resiliente
    script_data = generate_script_with_fallback(
        api_key=api_key,
        models=models,
        master_prompt=master_prompt,
        settings=settings,
        custom_prompt=custom_prompt,
        custom_titulo=custom_titulo
    )

    if not script_data:
        logger.error("Falha crítica na geração do roteiro. Abortando pipeline.")
        sys.exit(1)

    # Salva roteiro
    output_dir = base_dir / settings.get("output", {}).get("scripts_dir", "output/scripts")
    script_path = save_script(script_data, output_dir)

    # Exporta caminho para uso em steps seguintes do GitHub Actions
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"script_path={script_path}\n")
            f.write(f"script_title={script_data.get('titulo', 'Video')}\n")
            prompt_visual = script_data.get("prompt_visual", "")
            # Escapa quebras de linha para o GITHUB_OUTPUT
            prompt_visual_escaped = prompt_visual.replace("\n", " ").replace("\r", "")
            f.write(f"prompt_visual={prompt_visual_escaped}\n")

    logger.info("=== ROTEIRO GERADO COM SUCESSO ===")
    logger.info(f"Título: {script_data.get('titulo', 'N/A')}")
    logger.info(f"Modelo usado: {script_data.get('_meta', {}).get('model_used', 'N/A')}")
    logger.info(f"Arquivo: {script_path}")

    print(f"SCRIPT_PATH={script_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
