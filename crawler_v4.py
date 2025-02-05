import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import re
import pandas as pd
import time
import requests
import json
from bs4 import BeautifulSoup

def processar_resultados_tjba(decisoes, total_itens, total_paginas):
    """
    Processa a lista de decisões em um DataFrame.
    """
    resultados = []
    for decisao in decisoes:
        resultados.append({
            "Tribunal": "TJBA",
            "Número do Processo": decisao.get("numeroProcesso", "N/A"),
            "Relator": decisao.get("relator", {}).get("nome", "N/A"),
            "Órgão Julgador": decisao.get("orgaoJulgador", {}).get("nome", "N/A"),
            "Classe Processual": decisao.get("classe", {}).get("descricao", "N/A"),
            "Data da Publicação": decisao.get("dataPublicacao", "N/A"),
            #"Hash ID": decisao.get("hash", "N/A"),  # Identificador único
            "Ementa": decisao.get("conteudo", "N/A"),  # Texto completo
            #"Total de Itens": total_itens,
            #"Total de Páginas": total_paginas
        })

    return pd.DataFrame(resultados)

def processar_resultados_tjdf(json_result):
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
            "Identificador": registro.get("identificador", "N/A"),
            "Número do Processo": registro.get("processo", "N/A"),
            "Relator": registro.get("nomeRelator", "N/A"),
            "Órgão Julgador": registro.get("descricaoOrgaoJulgador", "N/A"),
            "Data do Julgamento": registro.get("dataJulgamento", "N/A"),
            "Data da Publicação": registro.get("dataPublicacao", "N/A"),
            "Ementa": registro.get("ementa", "N/A"),
            "Decisão": registro.get("decisao", "N/A"),
            "Local de Publicação": registro.get("localDePublicacao", "N/A"),
            "Segredo de Justiça": registro.get("segredoJustica", False),
            "Inteiro Teor": registro.get("inteiroTeorHtml", "N/A"),
            "Jurisprudência Relacionada": "; ".join(jurisprudencia_links) if jurisprudencia_links else "N/A",
            #"Possui Inteiro Teor": registro.get("possuiInteiroTeor", False),
        })

    return pd.DataFrame(resultados)

def processar_resultados_tjpr(html_result):
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
                "Número do Processo": processos[j],
                "Segredo de Justiça": segredo_justica[j],
                "Relator": relatores[j],
                "Cargo do Relator": cargos_relatores[j],
                "Órgão Julgador": orgaos[j],
                "Comarca": comarcas[j],
                "Data do Julgamento": datas_julgamento[j],
                "Data da Publicação": datas_publicacao[j],  # 🔥 Captura correta
                "Ementa": ementas[j],
                "Inteiro Teor": integras[j],
                "Documento Anexo": anexos[j]
            })

    return pd.DataFrame(dados_processos)

def processar_resultados_tjap(json_result):
    decisoes = json_result.get("dados", [])
    resultados = []

    for decisao in decisoes:
        resultados.append({
            "Tribunal": "TJAP",
            "Número do Processo": decisao.get("numeroano", "N/A"),
            "Relator": decisao.get("nomerelator", "N/A"),
            "Órgão Julgador": decisao.get("lotacao", "N/A"),
            "Classe Processual": decisao.get("classe", "N/A"),
            "Data do Julgamento": decisao.get("datajulgamento", "N/A"),
            "Ementa": decisao.get("textoementa", "N/A"),
            "Inteiro Teor": "N/A",
            "Documento Anexo": "N/A"
        })

    return pd.DataFrame(resultados)

def buscar_jurisprudencia_tjba(assunto):
    url = "https://jurisprudenciaws.tjba.jus.br/graphql"
    headers = {"Content-Type": "application/json"}
    
    pagina = 0
    resultados_completos = pd.DataFrame()

    while True:  # Continua até não haver mais resultados
        payload = {
            "operationName": "filter",
            "variables": {
                "decisaoFilter": {
                    "assunto": assunto,
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
                print(f"❌ Resposta inesperada da API na página {pagina}: {json_result}")
                break  # Interrompe a busca se a resposta for inválida

            # Extrai os dados relevantes
            filter_data = json_result["data"].get("filter", {})
            decisoes = filter_data.get("decisoes", [])

            if not decisoes:  # Se a API não retornar mais decisões, finaliza a busca
                print(f"✅ Nenhuma decisão encontrada na página {pagina}. Finalizando paginação.")
                break

            # Processa os dados
            pagina_df = processar_resultados_tjba(decisoes, filter_data.get("itemCount", 0), filter_data.get("pageCount", 0))
            resultados_completos = pd.concat([resultados_completos, pagina_df], ignore_index=True)

            # Avança para a próxima página
            pagina += 1

        except requests.exceptions.RequestException as e:
            print(f"❌ Erro ao acessar a API do TJBA: {e}")
            break  # Evita loop infinito em caso de erro

    return resultados_completos

def buscar_jurisprudencia_tjdf(termos):
    pagina = 0
    resultados_completos = pd.DataFrame()
    total_hits = 0

    try:
        json_result, total_hits = consultar_resultados_tjdf_por_pagina(termos, pagina)
        if not json_result:
            return resultados_completos

        while len(resultados_completos) < total_hits:
            json_result, _ = consultar_resultados_tjdf_por_pagina(termos, pagina)
            if json_result:
                pagina_df = processar_resultados_tjdf(json_result)
                resultados_completos = pd.concat([resultados_completos, pagina_df], ignore_index=True)
                pagina += 1
            else:
                break

    except Exception as e:
        st.error(f"Erro ao buscar TJDFT: {e}")

    return resultados_completos

    # Função para consultar resultados na API do TJDFT

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

def buscar_jurisprudencia_tjpr(termo):
    pagina = 1
    resultados_completos = pd.DataFrame()
    total_hits = 0

    try:
        # Primeira consulta para obter o total de registros
        html, total_hits = consultar_resultados_tjpr_por_pagina(termo, pagina)
        if not html or total_hits == 0:
            return resultados_completos
        while len(resultados_completos) < total_hits:
            html, _ = consultar_resultados_tjpr_por_pagina(termo, pagina)
            if html:
                pagina_df = processar_resultados_tjpr(html)
                resultados_completos = pd.concat([resultados_completos, pagina_df], ignore_index=True)
                pagina += 1
            else:
                break

    except Exception as e:
        print(f"Erro ao buscar TJPR: {e}")

    return resultados_completos

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

def buscar_jurisprudencia_tjap(assunto):
    url = "https://tucujuris.tjap.jus.br/api/publico/consultar-jurisprudencia"
    headers = {"Content-Type": "application/json"}
    payload = {"ementa": assunto}

    response = requests.post(url, headers=headers, json=payload)
    return processar_resultados_tjap(response.json() if response.status_code == 200 else {"error": "Falha na requisição"})

def buscar_jurisprudencias_unificadas(termos):

    st.write("Buscando jurisprudência no TJPR...")
    resultados_tjpr_df = buscar_jurisprudencia_tjpr(" ".join(termos))

    st.write("Buscando jurisprudência no TJDFT...")
    resultados_tjdf_df = buscar_jurisprudencia_tjdf(" ".join(termos))

    st.write("Buscando jurisprudência no TJBA...")
    resultados_tjba_df = buscar_jurisprudencia_tjba(" ".join(termos))
    
    st.write("Buscando jurisprudência no TJAP...")
    resultados_tjap_df = buscar_jurisprudencia_tjap(" ".join(termos))
    
    # Unificar todos os resultados
    resultados_unificados = pd.concat([resultados_tjdf_df, resultados_tjba_df, resultados_tjap_df, resultados_tjpr_df], ignore_index=True)
    total_resultados = len(resultados_unificados)

    return resultados_unificados, total_resultados

# Interface do Streamlit
st.title("TJSearch")
st.subheader("Consulta de Jurisprudência Unificada")
st.subheader("TJAP, TJBA, TJDFT, TJPR e TJSP")

palavras_chave_input = st.text_input("Palavras-chave (separadas por vírgula)")
palavras_chave = [p.strip() for p in palavras_chave_input.split(",") if p.strip()]

if st.button("Buscar") and palavras_chave:
    resultados_df, total_hits = buscar_jurisprudencias_unificadas(palavras_chave)
    st.write(f"Total de resultados: {total_hits}")
    st.write(resultados_df)