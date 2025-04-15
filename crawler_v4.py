import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import plotly.express as px
import re
import pandas as pd
import time
import requests
import json
import io
import os
from datetime import datetime

# 🔑 Configuração do 2Captcha
API_KEY = st.secrets["auth_token"]

# Variável global para armazenar o token do reCAPTCHA
captcha_token = None
captcha_expiration_time = 0  

# 🚗 Configuração do Selenium (Anti-detecção)
options = webdriver.ChromeOptions()
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--disable-extensions")
options.add_argument("--disable-popup-blocking")
options.add_argument("--disable-plugins-discovery")
options.add_argument("--incognito")
options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option('useAutomationExtension', False)

try:
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 30)
    # Ajuste anti-detecção
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                     'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    })
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
except Exception as e:
    st.error("⚠️ Ocorreu um problema ao configurar o navegador automático. Verifique sua conexão com a internet ou tente novamente mais tarde.")
    st.stop()


def buscar_jurisprudencias_unificadas(termos):

    resultados_unificados = pd.DataFrame()

    for termo in termos:

        st.write(f"> **BUSCA PELO TERMO {termo.upper()}**")

        st.write("🔍 Buscando jurisprudência no TJSP...")
        resultados_tjsp = buscar_jurisprudencia_tjsp(termo)
        st.write("✅ Busca concluída no TJSP...")

        st.write("🔍 Buscando jurisprudência no TJPR...")
        resultados_tjpr = buscar_jurisprudencia_tjpr(termo)
        st.write("✅ Busca concluída no TJPR...")

        st.write("🔍 Buscando jurisprudência no TJDFT...")
        resultados_tjdf = buscar_jurisprudencia_tjdf(termo)
        st.write("✅ Busca concluída no TJDFT...")

        st.write("🔍 Buscando jurisprudência no TJBA...")
        resultados_tjba = buscar_jurisprudencia_tjba(termo)
        st.write("✅ Busca concluída no TJBA...")

        st.write("🔍 Buscando jurisprudência no TJAP...")
        resultados_tjap = buscar_jurisprudencia_tjap(termo)
        st.write("✅ Busca concluída no TJAP...")

        resultados_unificados = pd.concat([resultados_tjsp, resultados_tjdf, resultados_tjba, resultados_tjap, resultados_tjpr, resultados_unificados], ignore_index=True)

    # Agrupa pelo número do processo e junta os termos únicos
    resultados_unificados = (
        resultados_unificados
        .groupby(['Número do Processo'], as_index=False)
        .agg({
            'Tribunal': 'first',
            'Relator': 'first',
            'Órgão Julgador': 'first',
            'Data da Publicação': 'first',
            'Ementa': 'first',
            'Termos': lambda x: ', '.join(sorted(set(x)))
        })
    )

    total_resultados = len(resultados_unificados)

    # 💾 Criar nome do arquivo com data e hora
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    nome_arquivo = f"resultados_{timestamp}.xlsx"
    caminho_arquivo = os.path.join("resultados", nome_arquivo)

    # Criar diretório se não existir
    os.makedirs("resultados", exist_ok=True)

    # Salvar arquivo local
    resultados_unificados.to_excel(caminho_arquivo, index=False)

    # Limpar arquivos antigos da pasta (opcional: só os que começam com 'resultados_')
    for arquivo in os.listdir("resultados"):
        if arquivo.startswith("resultados_") and arquivo != nome_arquivo:
            os.remove(os.path.join("resultados", arquivo))

    # Criar buffer para download no Streamlit
    buffer = io.BytesIO()
    resultados_unificados.to_excel(buffer, index=False, engine='xlsxwriter')
    buffer.seek(0)

    st.download_button(
        label=f"📥 Baixar resultados ({nome_arquivo})",
        data=buffer,
        file_name=nome_arquivo,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    return resultados_unificados, total_resultados

def buscar_jurisprudencia_tjsp(termo):
    global captcha_token

    # Sitekey do reCAPTCHA v3
    SITE_KEY = "6LcXJIAbAAAAAOwprTGEEYwRSe-HMYD-Ys0pSR6f"
    
    # 🔎 URL do site do TJSP
    URL_TJSP = "https://esaj.tjsp.jus.br/cjsg/consultaCompleta.do"

    # Se o token expirou, gerar um novo
    if not captcha_token or time.time() > captcha_expiration_time:
        resolver_captcha(URL_TJSP, SITE_KEY)
    
    pagina = 1
    j = 1
    while True:  # Tenta até conseguir acessar os dados
        try:
            status.info(f"📌 Buscando por: {termo} no TJSP")

            
            # 📌 1. Acessar a página do TJSP
            try:
                driver.get(URL_TJSP)
            except Exception as e:
                print(f"Erro ao carregar a página: {e}")
                continue

            # 📌 2. Preencher o campo de pesquisa
            search_box = wait.until(EC.presence_of_element_located((By.NAME, "dados.buscaInteiroTeor")))
            search_box.clear()
            search_box.send_keys(termo)

            # Inserir solução CAPTCHA na página
            driver.execute_script(
                "document.getElementById('id_recaptcha_response_token').value = arguments[0];",
                captcha_token
            )
            # Injeta o token no campo correto e garante que ele exista no DOM
            driver.execute_script("""
                let responseField = document.getElementsByName('g-recaptcha-response')[0];
                if (!responseField) {
                    responseField = document.createElement('textarea');
                    responseField.name = 'g-recaptcha-response';
                    responseField.style.display = 'none';
                    document.body.appendChild(responseField);
                }
                responseField.value = arguments[0];
            """, captcha_token)
            time.sleep(1)

            # 📌 3. Submeter o formulário
            pesquisar = wait.until(EC.element_to_be_clickable((By.NAME, "pbSubmit")))
            driver.execute_script("arguments[0].click();", pesquisar)
            time.sleep(2)

            html = driver.page_source
            with open("pagina_pos_submit.html", "w", encoding="utf-8") as f:
                f.write(html)

            # 📌 4. Extração de dados
            resultados_finais = []

            while True:
                status.info(f"📄 Extraindo dados da página {pagina} do TJSP...")

                time.sleep(5)

                # Verifica se há linhas de resultado
                linhas_resultado = driver.find_elements(By.CSS_SELECTOR, "tr.fundocinza1")
                
                if not linhas_resultado:
                    status.info(f"⚠️ Nenhum resultado encontrado na página {pagina}. Encerrando busca no TJSP.")
                    break

                soup = BeautifulSoup(driver.page_source, "html.parser")
                processos = soup.find_all("tr", class_="fundocinza1")

                for processo in processos:
                    status.info(f"✅ Pegando processo {j} do TJSP...")
                    dados = {}

                    processo_link = processo.find("a", class_="esajLinkLogin downloadEmenta")
                    if processo_link:
                        dados["numero_processo"] = processo_link.text.strip()
                        dados["cdacordao"] = processo_link.get("cdacordao", None)

                    if dados.get("cdacordao"):
                        ementa_div = soup.find("div", id=f"textAreaDados_{dados['cdacordao']}")
                        if ementa_div:
                            dados["ementa_curta"] = ementa_div.text.strip().split("  (TJSP")[0]

                    for tr in processo.find_all("tr", class_="ementaClass2"):
                        strong = tr.find("strong")
                        if strong:
                            chave = strong.text.strip().replace(":", "")
                            valor = tr.get_text().strip().replace(strong.text.strip(), "").strip()
                            if chave and valor:
                                dados[chave] = valor

                    resultados_finais.append(dados)
                    j += 1

                try:
                    proxima_pagina = driver.find_elements(By.LINK_TEXT, ">")
                    if proxima_pagina:
                        proxima_pagina[0].click()
                        time.sleep(3)
                        status.info(f"Avançando para a próxima página no TJSP...")
                        pagina += 1
                    else:
                        status.info(f"🔚 Última página alcançada no TJSP.")
                        break
                except:
                    status.error(f"Erro ao consultar a página #{pagina} do TJSP")
                    break
            try:
                return processar_resultados_tjsp(resultados_finais, termo)
            except:
                status.error(f"Erro ao extrair resultados do TJSP")
                break

        except Exception as e:
            status.info(f"⚠️ Erro ao acessar os dados ({e}), tentando novamente em 5s...")
            time.sleep(5)
            resolver_captcha(URL_TJSP, SITE_KEY)  # Gera um novo CAPTCHA antes de tentar novamente

def buscar_jurisprudencia_tjba(termo):
    url = "https://jurisprudenciaws.tjba.jus.br/graphql"
    headers = {"Content-Type": "application/json"}
    
    pagina = 0
    resultados_completos = pd.DataFrame()

    status.info(f"📌 Buscando por: {termo} no TJBA")

    while True:  # Continua até não haver mais resultados
        payload = {
            "operationName": "filter",
            "variables": {
                "decisaoFilter": {
                    "assunto": termo,
                    "ordenadoPor": "dataPublicacao"
                },
                "pageNumber": pagina,
                "itemsPerPage": 10
            },
            "query": """query filter($decisaoFilter: DecisaoFilter!, $pageNumber: Int!, $itemsPerPage: Int!) {
                filter(decisaoFilter: $decisaoFilter, pageNumber: $pageNumber, itemsPerPage: $itemsPerPage) {
                    decisoes {
                        dataPublicacao
                        relator { nome }
                        orgaoJulgador { nome }
                        classe { descricao }
                        conteudo
                        hash
                        numeroProcesso
                    }
                    pageCount
                    itemCount
                }
            }"""
        }

        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            json_result = response.json()

            # Verificação de erro na resposta
            if not json_result or "data" not in json_result or not isinstance(json_result["data"], dict):
                status.error(f"❌ Resposta inesperada da API na página do TJBA {pagina}: {json_result}")
                break  # Interrompe a busca se a resposta for inválida

            # Extrai os dados relevantes
            filter_data = json_result["data"].get("filter", {})
            decisoes = filter_data.get("decisoes", [])

            if not decisoes:  # Se a API não retornar mais decisões, finaliza a busca
                status.info(f"✅ Nenhuma decisão encontrada na página {pagina}. Finalizando paginação no TJBA.")
                break

            # Processa os dados
            pagina_df = processar_resultados_tjba(decisoes, filter_data.get("itemCount", 0), filter_data.get("pageCount", 0), termo)
            resultados_completos = pd.concat([resultados_completos, pagina_df], ignore_index=True)

            # Avança para a próxima página
            pagina += 1

            status.info(f"Processada a página #{pagina} do TJBA")

        except requests.exceptions.RequestException as e:
            print(f"❌ Erro ao acessar a API do TJBA: {e}")
            break  # Evita loop infinito em caso de erro

    return resultados_completos

def buscar_jurisprudencia_tjdf(termo):
    pagina = 0
    resultados_completos = pd.DataFrame()
    total_hits = 0

    status.info(f"📌 Buscando por: {termo} no TJDFT")

    try:
        json_result, total_hits = consultar_resultados_tjdf_por_pagina(termo, pagina)
        if not json_result:
            return resultados_completos

        while len(resultados_completos) < total_hits:
            json_result, _ = consultar_resultados_tjdf_por_pagina(termo, pagina)
            if json_result:
                pagina_df = processar_resultados_tjdf(json_result, termo)
                resultados_completos = pd.concat([resultados_completos, pagina_df], ignore_index=True)
                pagina += 1
                status.info(f"Processada a página #{pagina} do TJDFT")
            else:
                break

    except Exception as e:
        status.error(f"Erro ao buscar TJDFT: {e}")

    return resultados_completos

    # Função para consultar resultados na API do TJDFT

def buscar_jurisprudencia_tjpr(termo):
    pagina = 1
    resultados_completos = pd.DataFrame()
    total_hits = 0

    status.info(f"📌 Buscando por: {termo} no TJPR")

    try:
        # Primeira consulta para obter o total de registros
        html, total_hits = consultar_resultados_tjpr_por_pagina(termo, pagina)
        if not html or total_hits == 0:
            return resultados_completos
        while len(resultados_completos) < total_hits:
            html, _ = consultar_resultados_tjpr_por_pagina(termo, pagina)
            if html:
                pagina_df = processar_resultados_tjpr(html, termo)
                resultados_completos = pd.concat([resultados_completos, pagina_df], ignore_index=True)
                status.info(f"Processada a página #{pagina} do TJPR")
                pagina += 1
            else:
                break

    except Exception as e:
        status.error(f"Erro ao buscar TJPR: {e}")

    return resultados_completos

def buscar_jurisprudencia_tjap(termo):
    url = "https://tucujuris.tjap.jus.br/api/publico/consultar-jurisprudencia"
    headers = {"Content-Type": "application/json"}
    payload = {"ementa": termo}

    status.info(f"📌 Buscando por: {termo} no TJAP")

    response = requests.post(url, headers=headers, json=payload)
    return processar_resultados_tjap(response.json() if response.status_code == 200 else {"error": "Falha na requisição"}, termo)

def processar_resultados_tjsp(decisoes, termo):
    resultados = []
    for decisao in decisoes:
        resultados.append({
            "Tribunal": "TJSP",
            "Termos": termo,
            "Número do Processo": decisao.get("numero_processo", "N/A"),
            "Relator": decisao.get("Relator(a)", "N/A"),
            "Órgão Julgador": decisao.get("Órgão julgador", "N/A"),
            "Data da Publicação": decisao.get("Data de publicação", "N/A"),
            "Ementa": decisao.get("Ementa", "N/A"),
        })
    return pd.DataFrame(resultados)

def processar_resultados_tjba(decisoes, total_itens, total_paginas, termo):
    """
    Processa a lista de decisões em um DataFrame.
    """
    resultados = []
    for decisao in decisoes:
        resultados.append({
            "Tribunal": "TJBA",
            "Termos": termo,
            "Número do Processo": decisao.get("numeroProcesso", "N/A"),
            "Relator": decisao.get("relator", {}).get("nome", "N/A"),
            "Órgão Julgador": decisao.get("orgaoJulgador", {}).get("nome", "N/A"),
            "Data da Publicação": decisao.get("dataPublicacao", "N/A"),
            "Ementa": decisao.get("conteudo", "N/A"),  # Texto completo

            #"Classe Processual": decisao.get("classe", {}).get("descricao", "N/A"),
            #"Hash ID": decisao.get("hash", "N/A"),  # Identificador único
            #"Total de Itens": total_itens,
            #"Total de Páginas": total_paginas
        })

    return pd.DataFrame(resultados)

def processar_resultados_tjdf(json_result, termo):
    registros = json_result.get("registros", [])  # Lista de decisões
    resultados = []

    for registro in registros:
        jurisprudencia_links = []
        if registro.get("jurisprudenciaEmFoco"):
            jurisprudencia_links = [
                f"{item.get('descricao')}: {item.get('link')}"
                for item in registro.get("jurisprudenciaEmFoco", [])
            ]

        resultados.append({
            "Tribunal": "TJDFT",
            "Termos": termo,
            "Número do Processo": registro.get("processo", "N/A"),
            "Relator": registro.get("nomeRelator", "N/A"),
            "Órgão Julgador": registro.get("descricaoOrgaoJulgador", "N/A"),
            "Data da Publicação": registro.get("dataPublicacao", "N/A"),
            "Ementa": registro.get("ementa", "N/A")

            #"Data do Julgamento": registro.get("dataJulgamento", "N/A"),
            #"Identificador": registro.get("identificador", "N/A"),
            #"Decisão": registro.get("decisao", "N/A"),
            #"Local de Publicação": registro.get("localDePublicacao", "N/A"),
            #"Segredo de Justiça": registro.get("segredoJustica", False),
            #"Inteiro Teor": registro.get("inteiroTeorHtml", "N/A"),
            #"Jurisprudência Relacionada": "; ".join(jurisprudencia_links) if jurisprudencia_links else "N/A",
            #"Possui Inteiro Teor": registro.get("possuiInteiroTeor", False),
        })

    return pd.DataFrame(resultados)

def processar_resultados_tjpr(html_result, termo):
    if not html_result:
        return pd.DataFrame()

    # 📌 Divide o HTML em blocos baseados nas âncoras dos documentos
    documentos = re.split(r'<a name="DOC\d+"></a>', html_result)

    dados_processos = []

    for i, doc_html in enumerate(documentos[1:], start=1):
        doc_id = f"DOC{i + 1}"  # Nome do documento atual (DOC1, DOC2, etc.)

        # 📌 Captura o número do processo corretamente
        processos = re.findall(r'<b>Processo:</b>.*?<div[^>]*>\s*<div[^>]*>(.*?)</div>', doc_html, re.DOTALL)

        # 📌 Segredo de Justiça
        segredo_justica = re.findall(r'<b>Segredo de Justiça:</b>\s*(.*?)<', doc_html)

        # 📌 Captura nome do relator corretamente
        relatores = re.findall(r'<b>Relator\(a\):</b>\s*([\w\sÁÉÍÓÚáéíóúãõçü-]+)', doc_html)

        # 📌 Captura cargo do relator, se existir
        cargos_relatores = re.findall(r'<b>Relator\(a\):</b>.*?<i>(.*?)</i>', doc_html, re.DOTALL)

        # Se não houver cargo, preencher com "N/A"
        cargos_relatores += ["N/A"] * (len(relatores) - len(cargos_relatores))

        # 📌 Outros campos básicos
        orgaos = re.findall(r'<b>Órgão Julgador:</b>\s*(.*?)<', doc_html)
        comarcas = re.findall(r'<b>Comarca:</b>\s*(.*?)<', doc_html)
        datas_julgamento = re.findall(r'<b>Data do Julgamento:</b>\s*([\w\s:]+BRT\s\d{4})', doc_html)

        # 📌 Captura da Data da Publicação corrigida
        datas_publicacao = re.findall(r'<b>Fonte/Data da Publicação:</b>\s*&nbsp;([\w\s\d:]+BRT\s\d{4})', doc_html)

        ementas = re.findall(r'<div id="ementa\d+"[^>]*>(.*?)</div>', doc_html, re.DOTALL)
        integras = re.findall(r'<div\s+id="texto\d+"[^>]*>(.*?)<\/div>', doc_html, re.DOTALL | re.IGNORECASE)
        anexos = re.findall(r"document\.location\.replace\('(/jurisprudencia/publico/visualizacao\.do\?tjpr\.url\.crypto=[^']+)'\)", doc_html)

        # 📌 Limpeza de tags HTML
        ementas = [re.sub(r'<[^>]+>', '', e).strip() for e in ementas]
        integras = [re.sub(r'<[^>]+>', '', i).strip() for i in integras]
        anexos = ["https://portal.tjpr.jus.br" + link if link else "N/A" for link in anexos]

        # 📌 Ajustando tamanhos das listas
        max_len = max(len(processos), len(segredo_justica), len(relatores), len(cargos_relatores),
                      len(orgaos), len(comarcas), len(datas_julgamento), len(datas_publicacao),
                      len(ementas), len(integras), len(anexos), 1)  # Garante pelo menos uma entrada
        
        processos += ["N/A"] * (max_len - len(processos))
        segredo_justica += ["N/A"] * (max_len - len(segredo_justica))
        relatores += ["N/A"] * (max_len - len(relatores))
        cargos_relatores += ["N/A"] * (max_len - len(cargos_relatores))
        orgaos += ["N/A"] * (max_len - len(orgaos))
        comarcas += ["N/A"] * (max_len - len(comarcas))
        datas_julgamento += ["N/A"] * (max_len - len(datas_julgamento))
        datas_publicacao += ["N/A"] * (max_len - len(datas_publicacao))
        ementas += ["N/A"] * (max_len - len(ementas))
        integras += ["N/A"] * (max_len - len(integras))
        anexos += ["N/A"] * (max_len - len(anexos))

        for j in range(max_len):
            dados_processos.append({
                "Tribunal": "TJPR",
                "Termos": termo,
                "Número do Processo": processos[j],
                "Relator": relatores[j],
                "Órgão Julgador": orgaos[j],
                "Data da Publicação": datas_publicacao[j],  # 🔥 Captura correta
                "Ementa": ementas[j],

                #"Segredo de Justiça": segredo_justica[j],
                #"Cargo do Relator": cargos_relatores[j],
                #"Comarca": comarcas[j],
                #"Data do Julgamento": datas_julgamento[j],
                #"Inteiro Teor": integras[j],
                #"Documento Anexo": anexos[j]
            })

    return pd.DataFrame(dados_processos)

def processar_resultados_tjap(json_result, termo):
    decisoes = json_result.get("dados", [])
    resultados = []

    for decisao in decisoes:
        resultados.append({
            "Tribunal": "TJAP",
            "Termos": termo,
            "Número do Processo": decisao.get("numeroano", "N/A"),
            "Relator": decisao.get("nomerelator", "N/A"),
            "Órgão Julgador": decisao.get("lotacao", "N/A"),
            "Data da Publicação": decisao.get("datajulgamento", "N/A"),
            "Ementa": decisao.get("textoementa", "N/A"),

            #"Classe Processual": decisao.get("classe", "N/A"),
            #"Inteiro Teor": "N/A",
            #"Documento Anexo": "N/A"
        })

    return pd.DataFrame(resultados)

def consultar_resultados_tjdf_por_pagina(termos, pagina):
    url = "https://jurisdf.tjdft.jus.br/api/v1/pesquisa"
    payload = {
        "query": termos,
        "termosAcessorios": [],
        "pagina": pagina,
        "tamanho": 10,
        "sinonimos": True,
        "espelho": True,
        "inteiroTeor": True,
        "retornaInteiroTeor": False,
        "retornaTotalizacao": True
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()  # Isso levanta um erro se o status for >= 400
        json_result = response.json()
        total_hits = json_result.get("hits", {}).get("value", 0)
        return json_result, total_hits
    except requests.exceptions.HTTPError as e:
        if response.status_code == 500:
            st.warning("O servidor do TJDFT retornou um erro 500. Tentando continuar sem ele...")
        else:
            st.error(f"Erro ao acessar a API do TJDFT: {e}")
        return None, 0
    except requests.exceptions.RequestException as e:
        st.error(f"Erro de conexão com o TJDFT: {e}")
        return None, 0

def consultar_resultados_tjpr_por_pagina(termo, pagina):
    url = "https://portal.tjpr.jus.br/jurisprudencia/publico/pesquisa.do"
    params = {
        "actionType": "pesquisar",
        "criterioPesquisa": termo,
        "idLocalPesquisa": "1",
        "mostrarCompleto": "true",
        "iniciar": "Pesquisar",
        "pageSize": "10",
        "pageNumber": pagina
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        html = response.text

        # Extraindo o número total de registros usando regex
        match = re.search(r'(\d+)\s+registro\(s\)\s+encontrado\(s\)', html)
        total_registros = int(match.group(1)) if match else 0

        return html, total_registros

    except requests.RequestException as e:
        print(f"Erro ao acessar o TJPR: {e}")
        return None, 0

def resolver_captcha(url, site_key):
    global captcha_token, captcha_expiration_time
    print("🔄 Resolvendo CAPTCHA com 2Captcha...")

    while True:  # Loop infinito até resolver corretamente
        captcha_payload = {
            'key': API_KEY,
            'method': 'userrecaptcha',
            'version': 'v3',
            'action': 'consulta',
            'min_score': 0.3,
            'googlekey': site_key,
            'pageurl': url,
            'json': 1
        }
        captcha_response = requests.get('http://2captcha.com/in.php', params=captcha_payload).json()

        if captcha_response["status"] != 1:
            print("❌ Erro ao enviar CAPTCHA:", captcha_response["request"])
            time.sleep(5)
            continue

        captcha_id = captcha_response["request"]
        print(f"🆔 CAPTCHA enviado, ID: {captcha_id}")

        for _ in range(10):  # Espera até 50s
            solution_response = requests.get(
                f"http://2captcha.com/res.php?key={API_KEY}&action=get&id={captcha_id}&json=1"
            ).json()

            if solution_response["status"] == 1:
                captcha_token = solution_response["request"]
                captcha_expiration_time = time.time() + 120  # Token válido por 2 minutos
                print(f"✅ CAPTCHA resolvido: {captcha_token[:30]}... (truncado)")
                return

            print("⌛ Aguardando solução do CAPTCHA...")
            time.sleep(5)

        print("❌ CAPTCHA falhou, tentando novamente em 15s...")
        time.sleep(15)

# Interface do Streamlit
st.title("🔍 TJSearch")
st.subheader("Consulta de Jurisprudência Unificada")
st.subheader("TJAP, TJBA, TJDFT, TJPR e TJSP")
status = st.empty()  # espaço reservado na tela

palavras_chave_input = st.text_input("Palavras-chave (separadas por vírgula)")
palavras_chave = [p.strip() for p in palavras_chave_input.split(",") if p.strip()]

if st.button("Buscar") and palavras_chave:
    resultados_df, total_hits = buscar_jurisprudencias_unificadas(palavras_chave)
    st.write(f"Total de resultados: {total_hits}")
    st.write(resultados_df)

    # Gráfico de barras com Plotly
    contagem_tribunais = resultados_df['Tribunal'].value_counts(ascending=True).reset_index()
    contagem_tribunais.columns = ['Tribunal', 'Número de Resultados']

    fig = px.bar(contagem_tribunais, x='Tribunal', y='Número de Resultados', text='Número de Resultados',
                 title='Distribuição de Resultados por Tribunal')

    fig.update_traces(texttemplate='%{text}', textposition='outside')
    fig.update_layout(uniformtext_minsize=12, uniformtext_mode='hide', xaxis_title='Tribunal', yaxis_title='Número de Resultados',
                      xaxis_showgrid=False, yaxis_showgrid=False, font=dict(size=12))  # Aumenta o tamanho da fonte

    st.plotly_chart(fig)


# Variável global para armazenar o token do reCAPTCHA
captcha_token = None
captcha_expiration_time = 0  

# 🚗 Configuração do Selenium (Anti-detecção)
options = webdriver.ChromeOptions()
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--disable-extensions")
options.add_argument("--disable-popup-blocking")
options.add_argument("--disable-plugins-discovery")
options.add_argument("--incognito")
options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option('useAutomationExtension', False)

try:
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 30)
    # Ajuste anti-detecção
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                     'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    })
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
except Exception as e:
    st.error("⚠️ Ocorreu um problema ao configurar o navegador automático. Verifique sua conexão com a internet ou tente novamente mais tarde.")
    st.stop()

def buscar_jurisprudencias_unificadas(termos):

    resultados_unificados = pd.DataFrame()

    for termo in termos:

        st.write(f"> **BUSCA PELO TERMO {termo.upper()}**")

        st.write("🔍 Buscando jurisprudência no TJSP...")
        resultados_tjsp = buscar_jurisprudencia_tjsp(termo)
        st.write("✅ Busca concluída no TJSP...")

        st.write("🔍 Buscando jurisprudência no TJPR...")
        resultados_tjpr = buscar_jurisprudencia_tjpr(termo)
        st.write("✅ Busca concluída no TJPR...")

        st.write("🔍 Buscando jurisprudência no TJDFT...")
        resultados_tjdf = buscar_jurisprudencia_tjdf(termo)
        st.write("✅ Busca concluída no TJDFT...")

        st.write("🔍 Buscando jurisprudência no TJBA...")
        resultados_tjba = buscar_jurisprudencia_tjba(termo)
        st.write("✅ Busca concluída no TJBA...")

        st.write("🔍 Buscando jurisprudência no TJAP...")
        resultados_tjap = buscar_jurisprudencia_tjap(termo)
        st.write("✅ Busca concluída no TJAP...")

        resultados_unificados = pd.concat([resultados_tjsp, resultados_tjdf, resultados_tjba, resultados_tjap, resultados_tjpr, resultados_unificados], ignore_index=True)

    # Agrupa pelo número do processo e junta os termos únicos
    resultados_unificados = (
        resultados_unificados
        .groupby(['Número do Processo'], as_index=False)
        .agg({
            'Tribunal': 'first',
            'Relator': 'first',
            'Órgão Julgador': 'first',
            'Data da Publicação': 'first',
            'Ementa': 'first',
            'Termos': lambda x: ', '.join(sorted(set(x)))
        })
    )

    total_resultados = len(resultados_unificados)

    # 💾 Criar nome do arquivo com data e hora
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    nome_arquivo = f"resultados_{timestamp}.xlsx"
    caminho_arquivo = os.path.join("resultados", nome_arquivo)

    # Criar diretório se não existir
    os.makedirs("resultados", exist_ok=True)

    # Salvar arquivo local
    resultados_unificados.to_excel(caminho_arquivo, index=False)

    # Limpar arquivos antigos da pasta (opcional: só os que começam com 'resultados_')
    for arquivo in os.listdir("resultados"):
        if arquivo.startswith("resultados_") and arquivo != nome_arquivo:
            os.remove(os.path.join("resultados", arquivo))

    # Criar buffer para download no Streamlit
    buffer = io.BytesIO()
    resultados_unificados.to_excel(buffer, index=False, engine='xlsxwriter')
    buffer.seek(0)

    st.download_button(
        label=f"📥 Baixar resultados ({nome_arquivo})",
        data=buffer,
        file_name=nome_arquivo,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    return resultados_unificados, total_resultados

def buscar_jurisprudencia_tjsp(termo):
    global captcha_token

    # Sitekey do reCAPTCHA v3
    SITE_KEY = "6LcXJIAbAAAAAOwprTGEEYwRSe-HMYD-Ys0pSR6f"
    
    # 🔎 URL do site do TJSP
    URL_TJSP = "https://esaj.tjsp.jus.br/cjsg/consultaCompleta.do"

    # Se o token expirou, gerar um novo
    if not captcha_token or time.time() > captcha_expiration_time:
        resolver_captcha(URL_TJSP, SITE_KEY)
    
    pagina = 1
    j = 1
    while True:  # Tenta até conseguir acessar os dados
        try:
            status.info(f"📌 Buscando por: {termo} no TJSP")

            
            # 📌 1. Acessar a página do TJSP
            try:
                driver.get(URL_TJSP)
            except Exception as e:
                print(f"Erro ao carregar a página: {e}")
                continue

            # 📌 2. Preencher o campo de pesquisa
            search_box = wait.until(EC.presence_of_element_located((By.NAME, "dados.buscaInteiroTeor")))
            search_box.clear()
            search_box.send_keys(termo)

            # Inserir solução CAPTCHA na página
            driver.execute_script(
                "document.getElementById('id_recaptcha_response_token').value = arguments[0];",
                captcha_token
            )
            # Injeta o token no campo correto e garante que ele exista no DOM
            driver.execute_script("""
                let responseField = document.getElementsByName('g-recaptcha-response')[0];
                if (!responseField) {
                    responseField = document.createElement('textarea');
                    responseField.name = 'g-recaptcha-response';
                    responseField.style.display = 'none';
                    document.body.appendChild(responseField);
                }
                responseField.value = arguments[0];
            """, captcha_token)
            time.sleep(1)

            # 📌 3. Submeter o formulário
            pesquisar = wait.until(EC.element_to_be_clickable((By.NAME, "pbSubmit")))
            driver.execute_script("arguments[0].click();", pesquisar)
            time.sleep(2)

            html = driver.page_source
            with open("pagina_pos_submit.html", "w", encoding="utf-8") as f:
                f.write(html)

            # 📌 4. Extração de dados
            resultados_finais = []

            while True:
                status.info(f"📄 Extraindo dados da página {pagina} do TJSP...")

                time.sleep(5)

                # Verifica se há linhas de resultado
                linhas_resultado = driver.find_elements(By.CSS_SELECTOR, "tr.fundocinza1")
                
                if not linhas_resultado:
                    status.info(f"⚠️ Nenhum resultado encontrado na página {pagina}. Encerrando busca no TJSP.")
                    break

                soup = BeautifulSoup(driver.page_source, "html.parser")
                processos = soup.find_all("tr", class_="fundocinza1")

                for processo in processos:
                    status.info(f"✅ Pegando processo {j} do TJSP...")
                    dados = {}

                    processo_link = processo.find("a", class_="esajLinkLogin downloadEmenta")
                    if processo_link:
                        dados["numero_processo"] = processo_link.text.strip()
                        dados["cdacordao"] = processo_link.get("cdacordao", None)

                    if dados.get("cdacordao"):
                        ementa_div = soup.find("div", id=f"textAreaDados_{dados['cdacordao']}")
                        if ementa_div:
                            dados["ementa_curta"] = ementa_div.text.strip().split("  (TJSP")[0]

                    for tr in processo.find_all("tr", class_="ementaClass2"):
                        strong = tr.find("strong")
                        if strong:
                            chave = strong.text.strip().replace(":", "")
                            valor = tr.get_text().strip().replace(strong.text.strip(), "").strip()
                            if chave and valor:
                                dados[chave] = valor

                    resultados_finais.append(dados)
                    j += 1

                try:
                    proxima_pagina = driver.find_elements(By.LINK_TEXT, ">")
                    if proxima_pagina:
                        proxima_pagina[0].click()
                        time.sleep(3)
                        status.info(f"Avançando para a próxima página no TJSP...")
                        pagina += 1
                    else:
                        status.info(f"🔚 Última página alcançada no TJSP.")
                        break
                except:
                    status.error(f"Erro ao consultar a página #{pagina} do TJSP")
                    break
            try:
                return processar_resultados_tjsp(resultados_finais, termo)
            except:
                status.error(f"Erro ao extrair resultados do TJSP")
                break

        except Exception as e:
            status.info(f"⚠️ Erro ao acessar os dados ({e}), tentando novamente em 5s...")
            time.sleep(5)
            resolver_captcha(URL_TJSP, SITE_KEY)  # Gera um novo CAPTCHA antes de tentar novamente

def buscar_jurisprudencia_tjba(termo):
    url = "https://jurisprudenciaws.tjba.jus.br/graphql"
    headers = {"Content-Type": "application/json"}
    
    pagina = 0
    resultados_completos = pd.DataFrame()

    status.info(f"📌 Buscando por: {termo} no TJBA")

    while True:  # Continua até não haver mais resultados
        payload = {
            "operationName": "filter",
            "variables": {
                "decisaoFilter": {
                    "assunto": termo,
                    "ordenadoPor": "dataPublicacao"
                },
                "pageNumber": pagina,
                "itemsPerPage": 10
            },
            "query": """query filter($decisaoFilter: DecisaoFilter!, $pageNumber: Int!, $itemsPerPage: Int!) {
                filter(decisaoFilter: $decisaoFilter, pageNumber: $pageNumber, itemsPerPage: $itemsPerPage) {
                    decisoes {
                        dataPublicacao
                        relator { nome }
                        orgaoJulgador { nome }
                        classe { descricao }
                        conteudo
                        hash
                        numeroProcesso
                    }
                    pageCount
                    itemCount
                }
            }"""
        }

        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            json_result = response.json()

            # Verificação de erro na resposta
            if not json_result or "data" not in json_result or not isinstance(json_result["data"], dict):
                status.error(f"❌ Resposta inesperada da API na página do TJBA {pagina}: {json_result}")
                break  # Interrompe a busca se a resposta for inválida

            # Extrai os dados relevantes
            filter_data = json_result["data"].get("filter", {})
            decisoes = filter_data.get("decisoes", [])

            if not decisoes:  # Se a API não retornar mais decisões, finaliza a busca
                status.info(f"✅ Nenhuma decisão encontrada na página {pagina}. Finalizando paginação no TJBA.")
                break

            # Processa os dados
            pagina_df = processar_resultados_tjba(decisoes, filter_data.get("itemCount", 0), filter_data.get("pageCount", 0), termo)
            resultados_completos = pd.concat([resultados_completos, pagina_df], ignore_index=True)

            # Avança para a próxima página
            pagina += 1

            status.info(f"Processada a página #{pagina} do TJBA")

        except requests.exceptions.RequestException as e:
            print(f"❌ Erro ao acessar a API do TJBA: {e}")
            break  # Evita loop infinito em caso de erro

    return resultados_completos

def buscar_jurisprudencia_tjdf(termo):
    pagina = 0
    resultados_completos = pd.DataFrame()
    total_hits = 0

    status.info(f"📌 Buscando por: {termo} no TJDFT")

    try:
        json_result, total_hits = consultar_resultados_tjdf_por_pagina(termo, pagina)
        if not json_result:
            return resultados_completos

        while len(resultados_completos) < total_hits:
            json_result, _ = consultar_resultados_tjdf_por_pagina(termo, pagina)
            if json_result:
                pagina_df = processar_resultados_tjdf(json_result, termo)
                resultados_completos = pd.concat([resultados_completos, pagina_df], ignore_index=True)
                pagina += 1
                status.info(f"Processada a página #{pagina} do TJDFT")
            else:
                break

    except Exception as e:
        status.error(f"Erro ao buscar TJDFT: {e}")

    return resultados_completos

    # Função para consultar resultados na API do TJDFT

def buscar_jurisprudencia_tjpr(termo):
    pagina = 1
    resultados_completos = pd.DataFrame()
    total_hits = 0

    status.info(f"📌 Buscando por: {termo} no TJPR")

    try:
        # Primeira consulta para obter o total de registros
        html, total_hits = consultar_resultados_tjpr_por_pagina(termo, pagina)
        if not html or total_hits == 0:
            return resultados_completos
        while len(resultados_completos) < total_hits:
            html, _ = consultar_resultados_tjpr_por_pagina(termo, pagina)
            if html:
                pagina_df = processar_resultados_tjpr(html, termo)
                resultados_completos = pd.concat([resultados_completos, pagina_df], ignore_index=True)
                status.info(f"Processada a página #{pagina} do TJPR")
                pagina += 1
            else:
                break

    except Exception as e:
        status.error(f"Erro ao buscar TJPR: {e}")

    return resultados_completos

def buscar_jurisprudencia_tjap(termo):
    url = "https://tucujuris.tjap.jus.br/api/publico/consultar-jurisprudencia"
    headers = {"Content-Type": "application/json"}
    payload = {"ementa": termo}

    status.info(f"📌 Buscando por: {termo} no TJAP")

    response = requests.post(url, headers=headers, json=payload)
    return processar_resultados_tjap(response.json() if response.status_code == 200 else {"error": "Falha na requisição"}, termo)

def processar_resultados_tjsp(decisoes, termo):
    resultados = []
    for decisao in decisoes:
        resultados.append({
            "Tribunal": "TJSP",
            "Termos": termo,
            "Número do Processo": decisao.get("numero_processo", "N/A"),
            "Relator": decisao.get("Relator(a)", "N/A"),
            "Órgão Julgador": decisao.get("Órgão julgador", "N/A"),
            "Data da Publicação": decisao.get("Data de publicação", "N/A"),
            "Ementa": decisao.get("Ementa", "N/A"),
        })
    return pd.DataFrame(resultados)

def processar_resultados_tjba(decisoes, total_itens, total_paginas, termo):
    """
    Processa a lista de decisões em um DataFrame.
    """
    resultados = []
    for decisao in decisoes:
        resultados.append({
            "Tribunal": "TJBA",
            "Termos": termo,
            "Número do Processo": decisao.get("numeroProcesso", "N/A"),
            "Relator": decisao.get("relator", {}).get("nome", "N/A"),
            "Órgão Julgador": decisao.get("orgaoJulgador", {}).get("nome", "N/A"),
            "Data da Publicação": decisao.get("dataPublicacao", "N/A"),
            "Ementa": decisao.get("conteudo", "N/A"),  # Texto completo

            #"Classe Processual": decisao.get("classe", {}).get("descricao", "N/A"),
            #"Hash ID": decisao.get("hash", "N/A"),  # Identificador único
            #"Total de Itens": total_itens,
            #"Total de Páginas": total_paginas
        })

    return pd.DataFrame(resultados)

def processar_resultados_tjdf(json_result, termo):
    registros = json_result.get("registros", [])  # Lista de decisões
    resultados = []

    for registro in registros:
        jurisprudencia_links = []
        if registro.get("jurisprudenciaEmFoco"):
            jurisprudencia_links = [
                f"{item.get('descricao')}: {item.get('link')}"
                for item in registro.get("jurisprudenciaEmFoco", [])
            ]

        resultados.append({
            "Tribunal": "TJDFT",
            "Termos": termo,
            "Número do Processo": registro.get("processo", "N/A"),
            "Relator": registro.get("nomeRelator", "N/A"),
            "Órgão Julgador": registro.get("descricaoOrgaoJulgador", "N/A"),
            "Data da Publicação": registro.get("dataPublicacao", "N/A"),
            "Ementa": registro.get("ementa", "N/A")

            #"Data do Julgamento": registro.get("dataJulgamento", "N/A"),
            #"Identificador": registro.get("identificador", "N/A"),
            #"Decisão": registro.get("decisao", "N/A"),
            #"Local de Publicação": registro.get("localDePublicacao", "N/A"),
            #"Segredo de Justiça": registro.get("segredoJustica", False),
            #"Inteiro Teor": registro.get("inteiroTeorHtml", "N/A"),
            #"Jurisprudência Relacionada": "; ".join(jurisprudencia_links) if jurisprudencia_links else "N/A",
            #"Possui Inteiro Teor": registro.get("possuiInteiroTeor", False),
        })

    return pd.DataFrame(resultados)

def processar_resultados_tjpr(html_result, termo):
    if not html_result:
        return pd.DataFrame()

    # 📌 Divide o HTML em blocos baseados nas âncoras dos documentos
    documentos = re.split(r'<a name="DOC\d+"></a>', html_result)

    dados_processos = []

    for i, doc_html in enumerate(documentos[1:], start=1):
        doc_id = f"DOC{i + 1}"  # Nome do documento atual (DOC1, DOC2, etc.)

        # 📌 Captura o número do processo corretamente
        processos = re.findall(r'<b>Processo:</b>.*?<div[^>]*>\s*<div[^>]*>(.*?)</div>', doc_html, re.DOTALL)

        # 📌 Segredo de Justiça
        segredo_justica = re.findall(r'<b>Segredo de Justiça:</b>\s*(.*?)<', doc_html)

        # 📌 Captura nome do relator corretamente
        relatores = re.findall(r'<b>Relator\(a\):</b>\s*([\w\sÁÉÍÓÚáéíóúãõçü-]+)', doc_html)

        # 📌 Captura cargo do relator, se existir
        cargos_relatores = re.findall(r'<b>Relator\(a\):</b>.*?<i>(.*?)</i>', doc_html, re.DOTALL)

        # Se não houver cargo, preencher com "N/A"
        cargos_relatores += ["N/A"] * (len(relatores) - len(cargos_relatores))

        # 📌 Outros campos básicos
        orgaos = re.findall(r'<b>Órgão Julgador:</b>\s*(.*?)<', doc_html)
        comarcas = re.findall(r'<b>Comarca:</b>\s*(.*?)<', doc_html)
        datas_julgamento = re.findall(r'<b>Data do Julgamento:</b>\s*([\w\s:]+BRT\s\d{4})', doc_html)

        # 📌 Captura da Data da Publicação corrigida
        datas_publicacao = re.findall(r'<b>Fonte/Data da Publicação:</b>\s*&nbsp;([\w\s\d:]+BRT\s\d{4})', doc_html)

        ementas = re.findall(r'<div id="ementa\d+"[^>]*>(.*?)</div>', doc_html, re.DOTALL)
        integras = re.findall(r'<div\s+id="texto\d+"[^>]*>(.*?)<\/div>', doc_html, re.DOTALL | re.IGNORECASE)
        anexos = re.findall(r"document\.location\.replace\('(/jurisprudencia/publico/visualizacao\.do\?tjpr\.url\.crypto=[^']+)'\)", doc_html)

        # 📌 Limpeza de tags HTML
        ementas = [re.sub(r'<[^>]+>', '', e).strip() for e in ementas]
        integras = [re.sub(r'<[^>]+>', '', i).strip() for i in integras]
        anexos = ["https://portal.tjpr.jus.br" + link if link else "N/A" for link in anexos]

        # 📌 Ajustando tamanhos das listas
        max_len = max(len(processos), len(segredo_justica), len(relatores), len(cargos_relatores),
                      len(orgaos), len(comarcas), len(datas_julgamento), len(datas_publicacao),
                      len(ementas), len(integras), len(anexos), 1)  # Garante pelo menos uma entrada
        
        processos += ["N/A"] * (max_len - len(processos))
        segredo_justica += ["N/A"] * (max_len - len(segredo_justica))
        relatores += ["N/A"] * (max_len - len(relatores))
        cargos_relatores += ["N/A"] * (max_len - len(cargos_relatores))
        orgaos += ["N/A"] * (max_len - len(orgaos))
        comarcas += ["N/A"] * (max_len - len(comarcas))
        datas_julgamento += ["N/A"] * (max_len - len(datas_julgamento))
        datas_publicacao += ["N/A"] * (max_len - len(datas_publicacao))
        ementas += ["N/A"] * (max_len - len(ementas))
        integras += ["N/A"] * (max_len - len(integras))
        anexos += ["N/A"] * (max_len - len(anexos))

        for j in range(max_len):
            dados_processos.append({
                "Tribunal": "TJPR",
                "Termos": termo,
                "Número do Processo": processos[j],
                "Relator": relatores[j],
                "Órgão Julgador": orgaos[j],
                "Data da Publicação": datas_publicacao[j],  # 🔥 Captura correta
                "Ementa": ementas[j],

                #"Segredo de Justiça": segredo_justica[j],
                #"Cargo do Relator": cargos_relatores[j],
                #"Comarca": comarcas[j],
                #"Data do Julgamento": datas_julgamento[j],
                #"Inteiro Teor": integras[j],
                #"Documento Anexo": anexos[j]
            })

    return pd.DataFrame(dados_processos)

def processar_resultados_tjap(json_result, termo):
    decisoes = json_result.get("dados", [])
    resultados = []

    for decisao in decisoes:
        resultados.append({
            "Tribunal": "TJAP",
            "Termos": termo,
            "Número do Processo": decisao.get("numeroano", "N/A"),
            "Relator": decisao.get("nomerelator", "N/A"),
            "Órgão Julgador": decisao.get("lotacao", "N/A"),
            "Data da Publicação": decisao.get("datajulgamento", "N/A"),
            "Ementa": decisao.get("textoementa", "N/A"),

            #"Classe Processual": decisao.get("classe", "N/A"),
            #"Inteiro Teor": "N/A",
            #"Documento Anexo": "N/A"
        })

    return pd.DataFrame(resultados)

def consultar_resultados_tjdf_por_pagina(termos, pagina):
    url = "https://jurisdf.tjdft.jus.br/api/v1/pesquisa"
    payload = {
        "query": termos,
        "termosAcessorios": [],
        "pagina": pagina,
        "tamanho": 10,
        "sinonimos": True,
        "espelho": True,
        "inteiroTeor": True,
        "retornaInteiroTeor": False,
        "retornaTotalizacao": True
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()  # Isso levanta um erro se o status for >= 400
        json_result = response.json()
        total_hits = json_result.get("hits", {}).get("value", 0)
        return json_result, total_hits
    except requests.exceptions.HTTPError as e:
        if response.status_code == 500:
            st.warning("O servidor do TJDFT retornou um erro 500. Tentando continuar sem ele...")
        else:
            st.error(f"Erro ao acessar a API do TJDFT: {e}")
        return None, 0
    except requests.exceptions.RequestException as e:
        st.error(f"Erro de conexão com o TJDFT: {e}")
        return None, 0

def consultar_resultados_tjpr_por_pagina(termo, pagina):
    url = "https://portal.tjpr.jus.br/jurisprudencia/publico/pesquisa.do"
    params = {
        "actionType": "pesquisar",
        "criterioPesquisa": termo,
        "idLocalPesquisa": "1",
        "mostrarCompleto": "true",
        "iniciar": "Pesquisar",
        "pageSize": "10",
        "pageNumber": pagina
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        html = response.text

        # Extraindo o número total de registros usando regex
        match = re.search(r'(\d+)\s+registro\(s\)\s+encontrado\(s\)', html)
        total_registros = int(match.group(1)) if match else 0

        return html, total_registros

    except requests.RequestException as e:
        print(f"Erro ao acessar o TJPR: {e}")
        return None, 0

def resolver_captcha(url, site_key):
    global captcha_token, captcha_expiration_time
    print("🔄 Resolvendo CAPTCHA com 2Captcha...")

    while True:  # Loop infinito até resolver corretamente
        captcha_payload = {
            'key': API_KEY,
            'method': 'userrecaptcha',
            'version': 'v3',
            'action': 'consulta',
            'min_score': 0.3,
            'googlekey': site_key,
            'pageurl': url,
            'json': 1
        }
        captcha_response = requests.get('http://2captcha.com/in.php', params=captcha_payload).json()

        if captcha_response["status"] != 1:
            print("❌ Erro ao enviar CAPTCHA:", captcha_response["request"])
            time.sleep(5)
            continue

        captcha_id = captcha_response["request"]
        print(f"🆔 CAPTCHA enviado, ID: {captcha_id}")

        for _ in range(10):  # Espera até 50s
            solution_response = requests.get(
                f"http://2captcha.com/res.php?key={API_KEY}&action=get&id={captcha_id}&json=1"
            ).json()

            if solution_response["status"] == 1:
                captcha_token = solution_response["request"]
                captcha_expiration_time = time.time() + 120  # Token válido por 2 minutos
                print(f"✅ CAPTCHA resolvido: {captcha_token[:30]}... (truncado)")
                return

            print("⌛ Aguardando solução do CAPTCHA...")
            time.sleep(5)

        print("❌ CAPTCHA falhou, tentando novamente em 15s...")
        time.sleep(15)

# Interface do Streamlit
st.title("🔍 TJSearch")
st.subheader("Consulta de Jurisprudência Unificada")
st.subheader("TJAP, TJBA, TJDFT, TJPR e TJSP")
status = st.empty()  # espaço reservado na tela

palavras_chave_input = st.text_input("Palavras-chave (separadas por vírgula)")
palavras_chave = [p.strip() for p in palavras_chave_input.split(",") if p.strip()]

if st.button("Buscar") and palavras_chave:
    resultados_df, total_hits = buscar_jurisprudencias_unificadas(palavras_chave)
    st.write(f"Total de resultados: {total_hits}")
    st.write(resultados_df)

    # Gráfico de barras com Plotly
    contagem_tribunais = resultados_df['Tribunal'].value_counts(ascending=True).reset_index()
    contagem_tribunais.columns = ['Tribunal', 'Número de Resultados']

    fig = px.bar(contagem_tribunais, x='Tribunal', y='Número de Resultados', text='Número de Resultados',
                 title='Distribuição de Resultados por Tribunal')

    fig.update_traces(texttemplate='%{text}', textposition='outside')
    fig.update_layout(uniformtext_minsize=12, uniformtext_mode='hide', xaxis_title='Tribunal', yaxis_title='Número de Resultados',
                      xaxis_showgrid=False, yaxis_showgrid=False, font=dict(size=12))  # Aumenta o tamanho da fonte

    st.plotly_chart(fig)

