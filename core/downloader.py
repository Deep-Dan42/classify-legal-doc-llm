"""
automacao-juridica-trf1 — Downloader autenticado (TRF1 PJe)

Módulo responsável por:
  1. Abrir Chrome com perfil dedicado (undetected-chromedriver)
  2. Aguardar autenticação manual via whom.doc9
  3. Pesquisar CNPJs na consulta autenticada
  4. Filtrar processos por classe judicial e ano
  5. Extrair metadados do processo (empresa, CNPJ, classe, etc.)
  6. Listar documentos-alvo (DECISÃO, PETIÇÃO inicial)
  7. Baixar PDFs com deduplicação

Uso:
    from core.downloader import iniciar_navegador, aguardar_autenticacao

    driver = iniciar_navegador()
    aguardar_autenticacao(driver)
"""
from __future__ import annotations

import csv
import logging
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    NoAlertPresentException,
    UnexpectedAlertPresentException,
    StaleElementReferenceException,
)

from core.config import settings
from core.modelos import (
    TipoDocumento,
    RegistroDownload,
    DadosEmpresa,
)

logger = logging.getLogger(__name__)

# ============================================
# CONSTANTES
# ============================================

BASE_URL = "https://pje1g.trf1.jus.br"
URL_CONSULTA = f"{BASE_URL}/pje/Processo/ConsultaProcesso/listView.seam"
URL_PDF_TEMPLATE = f"{BASE_URL}/pje/seam/resource/rest/pje-legacy/documento/download/TRF1/1g/{{id_processo}}/{{id_documento}}"

# Classes judiciais permitidas (filtro na tabela de resultados)
CLASSES_PERMITIDAS = {
    "MANDADO DE SEGURANÇA CÍVEL",
    "PROCEDIMENTO COMUM CÍVEL",
}

# Padrão para extrair doc_id e nome do documento da timeline
# Uses search() not match() — handles leading whitespace, tree indents, unicode chars
RE_DOC_TIMELINE = re.compile(r"(\d{5,})\s*-\s*(.+)")

# Padrão para extrair CNPJ do texto do polo ativo/passivo
RE_CNPJ_TEXTO = re.compile(r"CNPJ:\s*([\d./-]+)")

# Padrão para extrair número de processo (NNNNNNN-NN.NNNN.N.NN.NNNN)
RE_NUMERO_PROCESSO = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")

# Timeouts (segundos)
TIMEOUT_PAGE_LOAD = 60
TIMEOUT_ELEMENT = 15
TIMEOUT_AJAX = 15          # Safety cap for WebDriverWait (actual response: 3-5s)
PAUSE_BETWEEN_ACTIONS = 1.5   # Conservative — used in navigation/forms (Sections 1-4)
PAUSE_BETWEEN_PROCESSES = 2.0
PAUSE_TIMELINE = 0.8          # Optimized — used only in timeline search/download (Section 5)

# Arquivo de flag para parada graciosa
# Criar este arquivo para interromper a automação após o processo atual:
#   touch data/saida/PARAR
STOP_FLAG_FILE = settings.DATA_SAIDA_DIR / "PARAR"


def _verificar_parada() -> bool:
    """
    Verifica se o usuário solicitou parada graciosa.
    Crie o arquivo data/saida/PARAR para interromper.
    O arquivo é removido automaticamente ao detectar.

    Retorna:
        True se deve parar.
    """
    if STOP_FLAG_FILE.exists():
        logger.info("⛔ Flag de parada detectada (data/saida/PARAR) — interrompendo após este processo")
        try:
            STOP_FLAG_FILE.unlink()
        except Exception:
            pass
        return True
    return False


# ============================================
# SEÇÃO 1: Browser setup + Auth + Popups
# ============================================

def iniciar_navegador():
    """
    Abre Chrome com perfil dedicado usando undetected-chromedriver.

    Retorna:
        driver: instância do Chrome WebDriver

    No Windows e macOS: Chrome pessoal pode permanecer aberto.
    O perfil de automação é isolado.
    """
    import platform
    import undetected_chromedriver as uc

    profile = str(settings.BROWSER_PROFILE_DIR / "chrome_automacao")
    sistema = platform.system()

    # Remover lock files do perfil de automação (podem ficar de sessão anterior)
    profile_path = Path(profile)
    profile_path.mkdir(parents=True, exist_ok=True)
    for lock_name in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
        lock_file = profile_path / lock_name
        if lock_file.exists():
            try:
                lock_file.unlink()
                logger.info(f"Lock removido: {lock_name}")
            except Exception:
                pass

    # Detectar caminho do Chrome por sistema operacional
    if sistema == "Darwin":  # macOS
        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    elif sistema == "Windows":
        # Caminhos comuns do Chrome no Windows
        candidatos = [
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        ]
        chrome_path = None
        for c in candidatos:
            if c.exists():
                chrome_path = str(c)
                break
        if not chrome_path:
            raise FileNotFoundError(
                "Google Chrome não encontrado. Instale o Chrome ou verifique a instalação.\n"
                f"Caminhos verificados: {[str(c) for c in candidatos]}"
            )
    else:
        chrome_path = "google-chrome"  # Linux

    # Detectar versão do Chrome
    ver = None
    if sistema == "Windows":
        # Windows: chrome.exe --version abre uma janela em vez de imprimir a versão
        # Ler versão do registro do Windows
        try:
            import winreg
            reg_path = r"SOFTWARE\Google\Chrome\BLBeacon"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
                version_str, _ = winreg.QueryValueEx(key, "version")
                ver = int(version_str.split(".")[0])
                logger.info(f"Chrome v{ver} (via registro do Windows)")
        except Exception:
            ver = None
            logger.info("Versão do Chrome não encontrada no registro — usando auto-detect")
    else:
        # macOS/Linux: --version funciona normalmente
        try:
            result = subprocess.run(
                [chrome_path, "--version"],
                capture_output=True, text=True, timeout=10,
            )
            ver = int(result.stdout.strip().split()[-1].split(".")[0])
        except Exception:
            ver = None
            logger.warning("Não foi possível detectar versão do Chrome — usando auto-detect")

    logger.info(f"Chrome {'v' + str(ver) if ver else '(auto)'} | {sistema} | Perfil: {profile}")

    # Windows: remove stale Chrome lock files from automation profile
    # (prevents "Chrome is already running" when personal Chrome is open)
    if sistema == "Windows":
        profile_path = Path(profile)
        profile_path.mkdir(parents=True, exist_ok=True)
        for lock_name in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
            lock_file = profile_path / lock_name
            if lock_file.exists():
                try:
                    lock_file.unlink()
                    logger.info(f"Lock removido: {lock_name}")
                except Exception:
                    pass

    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.page_load_strategy = "eager"

    # Configurar diretório de download
    download_dir = str(settings.DATA_DOCUMENTOS_DIR)
    Path(download_dir).mkdir(parents=True, exist_ok=True)
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,
        "profile.default_content_settings.popups": 0,
        "profile.default_content_setting_values.automatic_downloads": 1,
    }
    options.add_experimental_option("prefs", prefs)

    driver_kwargs = {
        "options": options,
        "user_data_dir": profile,
        "browser_executable_path": chrome_path,
        "driver_executable_path": None,
    }
    if ver:
        driver_kwargs["version_main"] = ver

    driver = uc.Chrome(**driver_kwargs)

    driver.set_page_load_timeout(TIMEOUT_PAGE_LOAD)
    driver.implicitly_wait(TIMEOUT_ELEMENT)

    # Forçar download de PDFs via Chrome DevTools Protocol
    try:
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": download_dir,
        })
        logger.info(f"CDP download configurado: {download_dir}")
    except Exception:
        logger.warning("CDP Page.setDownloadBehavior não disponível")

    logger.info("Chrome aberto com perfil de automação")
    return driver


def aguardar_autenticacao(driver, timeout: int = 300) -> bool:
    """
    Aguarda o usuário fazer login manual via whom.doc9.

    Detecta que a autenticação foi concluída quando a URL contém 'trf1' ou 'pje'.
    Timeout padrão: 5 minutos.

    Retorna:
        True se autenticado, False se timeout.
    """
    print("\n" + "=" * 50)
    print("  ETAPA MANUAL — Login via whom.doc9")
    print("=" * 50)
    print("  1. Clique no ícone whom.doc9 no Chrome")
    print("  2. Selecione 'JFAM - Pje - 1o grau'")
    print("  3. Clique 'Acessar'")
    print("  4. Aguarde o redirecionamento para o TRF1")
    print("=" * 50)

    inicio = time.time()
    while time.time() - inicio < timeout:
        try:
            # Verificar todas as abas
            for handle in driver.window_handles:
                driver.switch_to.window(handle)
                url = driver.current_url.lower()
                if any(kw in url for kw in ["trf1", "pje1g", "jus.br/pje"]):
                    logger.info(f"TRF1 detectado: {driver.current_url}")
                    print(f"\n  [OK] TRF1 detectado! URL: {driver.current_url[:60]}")
                    return True
        except Exception:
            pass
        time.sleep(2)

    logger.warning("Timeout aguardando autenticação whom.doc9")
    print("\n  [ERRO] Timeout — autenticação não detectada")
    return False


def fechar_popups(driver) -> None:
    """
    Fecha popups de aviso e certificado que aparecem após login no TRF1.

    Tenta 3 estratégias em sequência:
      1. Botão 'Fechar' (a[aria-label="Fechar"])
      2. JS: fecharPopupAlertaCertificadoProximoDeExpirar()
      3. Modal genérico (a[data-dismiss="modal"])
    """
    # Estratégia 1: Botão Fechar (aria-label)
    try:
        fechar_btns = driver.find_elements(By.CSS_SELECTOR, 'a[aria-label="Fechar"]')
        for btn in fechar_btns:
            try:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    logger.info("Popup fechado via a[aria-label='Fechar']")
                    time.sleep(0.5)
            except Exception:
                pass
    except Exception:
        pass

    # Estratégia 2: JS para popup de certificado
    try:
        driver.execute_script("fecharPopupAlertaCertificadoProximoDeExpirar();")
        logger.info("Popup certificado fechado via JS")
        time.sleep(0.5)
    except Exception:
        pass  # Função não existe = popup não apareceu

    # Estratégia 3: Modal genérico Bootstrap
    try:
        dismiss_btns = driver.find_elements(By.CSS_SELECTOR, '[data-dismiss="modal"]')
        for btn in dismiss_btns:
            try:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    logger.info("Modal genérico fechado via data-dismiss")
                    time.sleep(0.5)
            except Exception:
                pass
    except Exception:
        pass

    # Aceitar alert JS se houver
    try:
        alert = driver.switch_to.alert
        alert.accept()
        logger.info("Alert JS aceito")
    except NoAlertPresentException:
        pass


# ============================================
# SEÇÃO 2: Navegação + Pesquisa CNPJ
# ============================================

def _formatar_cnpj(cnpj: str) -> str:
    """
    Formata CNPJ para o padrão XX.XXX.XXX/XXXX-XX.
    Aceita entrada com ou sem formatação.
    """
    digits = re.sub(r"\D", "", cnpj)
    if len(digits) != 14:
        return digits  # Retorna como está se inválido
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:14]}"


def _so_digitos(cnpj: str) -> str:
    """Remove tudo que não é dígito."""
    return re.sub(r"\D", "", cnpj)


def navegar_para_consulta(driver) -> bool:
    """
    Navega diretamente para a URL de consulta de processos.
    Não precisa usar o menu — URL é acessível diretamente após auth.

    Retorna:
        True se a página carregou com o formulário de consulta.
    """
    logger.info(f"Navegando para consulta: {URL_CONSULTA}")
    driver.get(URL_CONSULTA)
    time.sleep(3)

    # Verificar se o formulário de consulta carregou
    try:
        WebDriverWait(driver, TIMEOUT_ELEMENT).until(
            EC.presence_of_element_located((By.ID, "fPP:dpDec:documentoParte"))
        )
        logger.info("Página de consulta carregada")
        return True
    except TimeoutException:
        logger.error("Formulário de consulta não carregou")
        return False


def pesquisar_cnpj(driver, cnpj: str) -> bool:
    """
    Preenche o formulário de consulta e pesquisa por CNPJ.

    Fluxo:
      1. Clicar radio CNPJ (ativa máscara jQuery)
      2. Preencher campo com CNPJ formatado via JS
      3. Clicar botão Pesquisar
      4. Aguardar tabela de resultados

    Args:
        cnpj: CNPJ com ou sem formatação

    Retorna:
        True se a pesquisa retornou resultados.
    """
    digits = _so_digitos(cnpj)
    formatado = _formatar_cnpj(cnpj)
    logger.info(f"Pesquisando CNPJ: {formatado}")

    # ── 1. Clicar radio CNPJ ──
    try:
        radio = driver.find_element(By.ID, "cnpj")
        driver.execute_script("arguments[0].click();", radio)
        # Disparar mascaraDocumento() para ativar o jQuery mask no campo
        driver.execute_script("mascaraDocumento();")
        time.sleep(PAUSE_BETWEEN_ACTIONS)
        logger.info("Radio CNPJ selecionado + máscara ativada")
    except Exception as e:
        logger.error(f"Erro ao clicar radio CNPJ: {e}")
        return False

    # ── 2. Preencher campo CNPJ ──
    campo_id = "fPP:dpDec:documentoParte"
    try:
        campo = driver.find_element(By.ID, campo_id)

        # Abordagem: limpar campo via JS, definir valor formatado, disparar eventos
        # O jQuery mask espera formato XX.XXX.XXX/XXXX-XX
        driver.execute_script(
            """
            var el = arguments[0];
            var val = arguments[1];
            // Limpar
            el.value = '';
            // Setar valor formatado
            el.value = val;
            // Disparar eventos que o RichFaces/jQuery escutam
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            el.dispatchEvent(new Event('blur', {bubbles: true}));
            """,
            campo, formatado,
        )
        time.sleep(0.5)

        # Verificar se o valor foi aceito
        valor_atual = campo.get_attribute("value")
        if not valor_atual or len(re.sub(r"\D", "", valor_atual)) < 11:
            # Fallback: tentar com apenas dígitos
            logger.warning(f"Valor não aceito ('{valor_atual}'). Tentando só dígitos...")
            driver.execute_script(
                """
                var el = arguments[0];
                el.value = '';
                el.value = arguments[1];
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.dispatchEvent(new Event('blur', {bubbles: true}));
                """,
                campo, digits,
            )
            time.sleep(0.5)

        valor_final = campo.get_attribute("value")
        logger.info(f"CNPJ preenchido: '{valor_final}'")

    except Exception as e:
        logger.error(f"Erro ao preencher CNPJ: {e}")
        return False

    # ── 3. Clicar Pesquisar ──
    try:
        btn = driver.find_element(By.ID, "fPP:searchProcessos")
        driver.execute_script("arguments[0].click();", btn)
        logger.info("Botão Pesquisar clicado")
    except Exception as e:
        logger.error(f"Erro ao clicar Pesquisar: {e}")
        return False

    # ── 4. Aguardar resultados ──
    # O A4J.AJAX do botão Pesquisar é assíncrono. Pipeline completo:
    # executarReCaptcha() → A4J.AJAX.Submit → server search → DOM update
    # Isso leva 5-8 segundos. Precisamos esperar o ciclo inteiro.

    # Primeiro: pausa mínima para o A4J iniciar (reCAPTCHA + submit)
    time.sleep(5)

    # Segundo: aguardar o loading do RichFaces concluir
    try:
        WebDriverWait(driver, TIMEOUT_AJAX).until(
            lambda d: d.execute_script(
                "var el = document.getElementById('modalStatusContainer');"
                "return !el || el.style.display === 'none' || el.style.display === '';"
            )
        )
    except TimeoutException:
        pass
    time.sleep(1)  # Margem para DOM se estabilizar após AJAX

    # Terceiro: esperar tabela com rows OU mensagem de aviso
    try:
        WebDriverWait(driver, TIMEOUT_ELEMENT).until(
            lambda d: (
                # Tabela com linhas de dados reais (td com classe rich-table-cell)
                len(d.find_elements(By.CSS_SELECTOR,
                    "#fPP\\:processosTable tbody tr td.rich-table-cell")) > 0
                # OU mensagem de aviso visível (nenhum resultado)
                or d.find_elements(By.CSS_SELECTOR,
                    "#fPP\\:j_id496[style*='display: block']")
                or d.find_elements(By.CSS_SELECTOR,
                    "#fPP\\:j_id496:not([style*='display: none'])")
            )
        )
    except TimeoutException:
        logger.warning("Timeout aguardando resultados da pesquisa")

    # Verificar se há resultados (usar rich-table-cell para confirmar rows reais)
    rows = driver.find_elements(By.CSS_SELECTOR, "#fPP\\:processosTable tbody tr")
    real_rows = driver.find_elements(
        By.CSS_SELECTOR, "#fPP\\:processosTable tbody tr td.rich-table-cell"
    )
    if not real_rows:
        logger.info(f"Nenhum processo encontrado para CNPJ {formatado}")
        return False

    # Extrair contagem do rodapé (ex: "40 resultados encontrados.")
    try:
        rodape = driver.find_element(
            By.CSS_SELECTOR, "#fPP\\:processosTable tfoot .text-muted"
        )
        logger.info(f"Resultados: {rodape.text.strip()}")
    except Exception:
        logger.info(f"Processos na tabela: {len(rows)} linhas visíveis")

    return True


# ============================================
# SEÇÃO 3: Tabela de processos + Filtros + Paginação
# ============================================

def extrair_processos_tabela(driver) -> list[dict]:
    """
    Extrai todas as linhas da tabela de processos da página ATUAL.

    Cada processo retornado é um dict com:
        - id_processo: str (ID interno do PJe, ex: "12332965")
        - numero_processo: str (ex: "1003965-30.2025.4.01.3200")
        - classe_judicial: str (ex: "MANDADO DE SEGURANÇA CÍVEL")
        - orgao_julgador: str
        - data_autuacao: str (ex: "31/01/2025")
        - polo_ativo: str
        - polo_passivo: str
        - ultima_movimentacao: str

    Retorna:
        Lista de dicts com dados de cada processo.
    """
    processos = []

    rows = driver.find_elements(By.CSS_SELECTOR, "#fPP\\:processosTable tbody tr")
    logger.info(f"Linhas na tabela (página atual): {len(rows)}")

    for row in rows:
        try:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) < 9:
                logger.info(f"Linha com {len(cells)} células ignorada (esperava 9)")
                continue

            # Extrair id_processo do ID de uma célula
            # Padrão: fPP:processosTable:{id_processo}:j_id507
            cell_id = cells[1].get_attribute("id") or ""
            id_match = re.search(r"processosTable:(\d+):", cell_id)
            id_processo = id_match.group(1) if id_match else ""

            # Extrair número do processo do link (atributo title)
            numero_processo = ""
            try:
                link = cells[1].find_element(By.TAG_NAME, "a")
                numero_processo = link.get_attribute("title") or link.text.strip()
            except Exception:
                numero_processo = cells[1].text.strip()

            processo = {
                "id_processo": id_processo,
                "numero_processo": numero_processo,
                "classe_judicial": cells[5].text.strip(),
                "orgao_julgador": cells[3].text.strip(),
                "data_autuacao": cells[4].text.strip(),
                "polo_ativo": cells[6].text.strip(),
                "polo_passivo": cells[7].text.strip(),
                "ultima_movimentacao": cells[8].text.strip(),
            }

            # Fallback: if classe_judicial is empty after AJAX pagination,
            # try JS-based innerText extraction (more reliable on stale DOM)
            if not processo["classe_judicial"]:
                try:
                    classe_js = driver.execute_script(
                        "return arguments[0].innerText;", cells[5]
                    )
                    processo["classe_judicial"] = (classe_js or "").strip()
                except Exception:
                    pass

            # Skip rows without valid id_processo (structural/empty rows)
            if not id_processo:
                logger.info(f"Linha sem id_processo ignorada: {numero_processo}")
                continue

            processos.append(processo)

        except Exception as e:
            # Catch ALL exceptions — not just StaleElement/IndexError
            # Prevents one bad row from losing all subsequent processes
            logger.warning(f"Erro ao ler linha da tabela (continuando): {type(e).__name__}: {e}")
            continue

    # Diagnostic: show all extracted processes
    if processos:
        nums = [p["numero_processo"] for p in processos]
        logger.info(f"Processos extraídos da tabela ({len(processos)}): {', '.join(nums)}")

    return processos


def _extrair_ano_autuacao(data_str: str) -> int:
    """
    Extrai o ano de uma data no formato DD/MM/YYYY.
    Retorna 0 se não conseguir parsear.
    """
    try:
        partes = data_str.strip().split("/")
        if len(partes) == 3:
            return int(partes[2])
    except (ValueError, IndexError):
        pass
    return 0


def filtrar_processos(processos: list[dict]) -> list[dict]:
    """
    Filtra processos por:
      1. Classe judicial: apenas CLASSES_PERMITIDAS
      2. Ano de autuação: >= settings.MIN_PROCESS_YEAR (default 2016)

    Retorna:
        Lista filtrada de processos.
    """
    filtrados = []
    for p in processos:
        classe = p.get("classe_judicial", "")
        ano = _extrair_ano_autuacao(p.get("data_autuacao", ""))

        # Filtro: classe permitida
        # Empty classe = DOM timing issue after pagination — accept the process
        if classe and classe not in CLASSES_PERMITIDAS:
            logger.info(f"Processo {p['numero_processo']} filtrado — classe '{classe}'")
            continue

        # Filtro: ano mínimo
        if ano == 0:
            # Fallback: extract year from process number (format: NNNNNNN-NN.YYYY.N.NN.NNNN)
            num = p.get("numero_processo", "")
            partes_num = num.split(".")
            if len(partes_num) >= 2:
                try:
                    ano = int(partes_num[1])
                except ValueError:
                    pass
        if ano > 0 and ano < settings.MIN_PROCESS_YEAR:
            logger.info(f"Processo {p['numero_processo']} filtrado — ano {ano}")
            continue

        filtrados.append(p)

    logger.info(
        f"Processos filtrados: {len(filtrados)} de {len(processos)} "
        f"(classes: {CLASSES_PERMITIDAS}, ano >= {settings.MIN_PROCESS_YEAR})"
    )
    return filtrados


def _tem_proxima_pagina(driver) -> bool:
    """
    Verifica se existe próxima página na paginação da tabela.

    A próxima página existe se há um td com classe 'rich-datascr-button'
    (sem 'dsbld') cujo onclick contém 'next'.
    """
    try:
        paginador = driver.find_element(By.ID, "fPP:processosTable:scTabela_table")
        cells = paginador.find_elements(By.TAG_NAME, "td")
        for cell in cells:
            classes = cell.get_attribute("class") or ""
            onclick = cell.get_attribute("onclick") or ""
            if "rich-datascr-button" in classes and "dsbld" not in classes and "'next'" in onclick:
                return True
    except Exception:
        pass
    return False


def _ir_proxima_pagina(driver) -> bool:
    """
    Clica no botão 'próxima página' da paginação.

    Retorna:
        True se navegou para próxima página.
    """
    try:
        paginador = driver.find_element(By.ID, "fPP:processosTable:scTabela_table")
        cells = paginador.find_elements(By.TAG_NAME, "td")
        for cell in cells:
            classes = cell.get_attribute("class") or ""
            onclick = cell.get_attribute("onclick") or ""
            if "rich-datascr-button" in classes and "dsbld" not in classes and "'next'" in onclick:
                driver.execute_script("arguments[0].click();", cell)
                logger.info("Navegando para próxima página de resultados")

                # Aguardar AJAX da paginação (conservative)
                time.sleep(5)

                # Aguardar loading RichFaces concluir
                try:
                    WebDriverWait(driver, TIMEOUT_AJAX).until(
                        lambda d: d.execute_script(
                            "var el = document.getElementById('modalStatusContainer');"
                            "return !el || el.style.display === 'none' || el.style.display === '';"
                        )
                    )
                except TimeoutException:
                    pass
                time.sleep(1)

                # Esperar tabela atualizar (tbody ter linhas reais)
                WebDriverWait(driver, TIMEOUT_ELEMENT).until(
                    lambda d: len(d.find_elements(
                        By.CSS_SELECTOR, "#fPP\\:processosTable tbody tr td.rich-table-cell"
                    )) > 0
                )
                return True
    except Exception as e:
        logger.warning(f"Erro ao navegar para próxima página: {e}")
    return False


def iterar_paginas_processos(driver):
    """
    Itera página por página da tabela de resultados.
    Para cada página, extrai e filtra processos, retornando a lista.

    IMPORTANTE: os processos retornados estão NO DOM da página atual.
    O chamador deve processar (abrir, scrape, download) TODOS os processos
    de uma página ANTES de chamar next() para ir à próxima.

    Yields:
        (pagina: int, processos: list[dict]) — processos filtrados da página atual.
    """
    pagina = 1
    while True:
        logger.info(f"Processando página {pagina} da tabela de resultados")

        processos_pagina = extrair_processos_tabela(driver)
        filtrados_pagina = filtrar_processos(processos_pagina)

        yield pagina, filtrados_pagina

        if _tem_proxima_pagina(driver):
            if _ir_proxima_pagina(driver):
                pagina += 1
                continue
            else:
                break
        else:
            break

    logger.info(f"Paginação concluída — {pagina} página(s) processadas")


# ============================================
# SEÇÃO 4: Abrir processo + Extrair metadados
# ============================================

def abrir_processo(driver, processo: dict, aba_consulta: str) -> Optional[str]:
    """
    Abre um processo clicando no link da tabela de resultados.
    Processo SEMPRE abre em nova aba.

    Args:
        processo: dict com 'id_processo' e 'numero_processo'
        aba_consulta: handle da aba de consulta

    Retorna:
        Handle da nova aba do processo, ou None se falhou.
    """
    id_proc = processo["id_processo"]
    num_proc = processo["numero_processo"]
    logger.info(f"Abrindo processo {num_proc} (id={id_proc})")

    # Garantir que estamos na aba de consulta
    driver.switch_to.window(aba_consulta)
    time.sleep(PAUSE_BETWEEN_ACTIONS)

    # Verificar que a tabela está no DOM
    try:
        WebDriverWait(driver, TIMEOUT_ELEMENT).until(
            EC.presence_of_element_located((By.ID, "fPP:processosTable"))
        )
    except TimeoutException:
        logger.error("Tabela de processos não encontrada")
        return None

    # Registrar abas antes do clique
    abas_antes = set(driver.window_handles)

    # ── Clicar no link do processo ──
    link_id = f"fPP:processosTable:{id_proc}:j_id509"

    try:
        link = driver.find_element(By.ID, link_id)
    except NoSuchElementException:
        logger.error(f"Link não encontrado: {link_id}")
        return None

    # Scroll para visibilidade
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});",
            link,
        )
        time.sleep(0.3)
    except Exception:
        pass

    # Click: real primeiro, fallback JS
    clicou = False
    try:
        link.click()
        clicou = True
    except Exception:
        pass
    if not clicou:
        try:
            driver.execute_script("arguments[0].click();", link)
            clicou = True
        except Exception as e:
            logger.error(f"Click falhou para {num_proc}: {e}")
            return None

    # ── PASSO 1: Aguardar e aceitar alert (até 20s) ──
    try:
        WebDriverWait(driver, 20).until(EC.alert_is_present())
        alert = driver.switch_to.alert
        alert.accept()
        logger.info("Alert aceito")
    except TimeoutException:
        logger.info("Nenhum alert em 20s")
    except NoAlertPresentException:
        pass
    except UnexpectedAlertPresentException:
        try:
            driver.switch_to.alert.accept()
            logger.info("Alert aceito (unexpected)")
        except Exception:
            pass

    time.sleep(PAUSE_BETWEEN_ACTIONS)

    # ── PASSO 2: Aguardar nova aba (até 15s) ──
    nova_aba = None
    try:
        WebDriverWait(driver, 15).until(
            lambda d: len(d.window_handles) > len(abas_antes)
        )
        novas_abas = set(driver.window_handles) - abas_antes
        if novas_abas:
            nova_aba = novas_abas.pop()
            logger.info("Nova aba detectada")
    except TimeoutException:
        logger.error(f"Processo {num_proc}: nenhuma nova aba em 15s")
    except UnexpectedAlertPresentException:
        try:
            driver.switch_to.alert.accept()
            logger.info("Alert tardio aceito")
            time.sleep(2)
            novas_abas = set(driver.window_handles) - abas_antes
            if novas_abas:
                nova_aba = novas_abas.pop()
        except Exception:
            pass

    if nova_aba is None:
        logger.error(f"Processo {num_proc} não abriu")
        return None

    # ── PASSO 3: Mudar para nova aba ──
    driver.switch_to.window(nova_aba)
    time.sleep(PAUSE_BETWEEN_PROCESSES)

    # Aceitar possível segundo alert na nova aba
    try:
        alert = driver.switch_to.alert
        alert.accept()
        logger.info("Segundo alert aceito")
        time.sleep(PAUSE_BETWEEN_ACTIONS)
    except (NoAlertPresentException, Exception):
        pass

    # ── PASSO 4: Aguardar página do processo carregar ──
    try:
        WebDriverWait(driver, TIMEOUT_ELEMENT).until(
            EC.presence_of_element_located((By.ID, "divTimeLine"))
        )
        logger.info(f"Processo carregado: {driver.current_url[:80]}")
    except TimeoutException:
        logger.warning(f"divTimeLine não encontrado para {num_proc} — tentando continuar")

    return nova_aba


def fechar_aba_processo(driver, aba_processo: str, aba_consulta: str) -> None:
    """
    Fecha a aba do processo e volta para a aba de consulta.
    Verifica que a tabela de resultados está acessível antes de retornar.
    """
    # Fechar aba do processo
    try:
        driver.switch_to.window(aba_processo)
        driver.close()
    except Exception:
        pass

    # Voltar para aba de consulta
    try:
        driver.switch_to.window(aba_consulta)
    except Exception:
        if driver.window_handles:
            driver.switch_to.window(driver.window_handles[0])

    # Verificar que a tabela de resultados está acessível
    # (previne stale DOM no próximo abrir_processo)
    try:
        WebDriverWait(driver, TIMEOUT_ELEMENT).until(
            EC.presence_of_element_located((By.ID, "fPP:processosTable"))
        )
    except TimeoutException:
        logger.warning("Tabela de resultados não encontrada após fechar processo")


def _extrair_id_processo_da_pagina(driver) -> str:
    """
    Extrai o idProcesso da variável JS na página de detalhe do processo.
    Necessário para construir a URL de download de documentos.

    Fonte no HTML: idProcesso: 12332965,
    """
    try:
        page_source = driver.page_source
        match = re.search(r"idProcesso:\s*(\d+)", page_source)
        if match:
            return match.group(1)
    except Exception:
        pass

    # Fallback: extrair da URL
    # URL padrão: .../Detalhe/listProcessoCompletoAdvogado.seam?id=12332965&...
    try:
        url = driver.current_url
        match = re.search(r"[?&]id=(\d+)", url)
        if match:
            return match.group(1)
    except Exception:
        pass

    return ""


def extrair_metadados_processo(driver, processo: dict) -> DadosEmpresa:
    """
    Extrai metadados da página de detalhe do processo.

    Abre o dropdown de detalhes (clicando no número do processo na barra de topo)
    e lê os campos de:
      - div#maisDetalhes: Classe judicial, Assunto, Jurisdição,
        Autuação, Valor da causa, Órgão julgador
      - div#poloAtivo: Empresa + CNPJ + Advogado
      - div#poloPassivo: Partes passivas

    Campos preenchidos no DadosEmpresa:
      - empresa, cnpj, advogado
      - local_processo (= Jurisdição / Órgão julgador)

    Campos NÃO disponíveis nesta view (ficam vazios):
      - cidade_uf_matriz, atividade_principal, atividade_secundaria, capital_social

    Também enriquece o dict `processo` com metadados adicionais:
      - classe_judicial, assunto, jurisdicao, orgao_julgador,
        valor_da_causa, autuacao (do detalhe, mais completo que da tabela)

    Args:
        processo: dict do processo (será enriquecido in-place)

    Retorna:
        DadosEmpresa com os campos disponíveis.
    """
    dados = DadosEmpresa()

    # ── Abrir dropdown de detalhes ──
    try:
        toggle = driver.find_element(
            By.CSS_SELECTOR, "a.titulo-topo.dropdown-toggle.titulo-topo-desktop"
        )
        driver.execute_script("arguments[0].click();", toggle)
        time.sleep(0.8)
    except Exception as e:
        logger.warning(f"Não conseguiu abrir dropdown de detalhes: {e}")
        # Continuar mesmo assim — metadados podem estar visíveis

    # ── div#maisDetalhes: campos dt/dd ──
    campos_mapeados = {}
    try:
        container = driver.find_element(By.ID, "maisDetalhes")
        dts = container.find_elements(By.TAG_NAME, "dt")

        for dt_el in dts:
            try:
                dt_text = dt_el.text.strip()
                if not dt_text:
                    continue
                dd_el = dt_el.find_element(By.XPATH, "following-sibling::dd[1]")
                dd_text = dd_el.text.strip()
                campos_mapeados[dt_text] = dd_text
            except Exception:
                continue

        logger.info(f"Metadados dt/dd encontrados: {list(campos_mapeados.keys())}")

    except NoSuchElementException:
        logger.warning("div#maisDetalhes não encontrado")

    # Preencher metadados no dict do processo
    processo["classe_judicial_detalhe"] = campos_mapeados.get("Classe judicial", "")
    processo["assunto"] = campos_mapeados.get("Assunto", "")
    processo["jurisdicao"] = campos_mapeados.get("Jurisdição", "")
    processo["orgao_julgador_detalhe"] = campos_mapeados.get("Órgão julgador", "")
    processo["valor_da_causa"] = campos_mapeados.get("Valor da causa", "")
    processo["autuacao_detalhe"] = campos_mapeados.get("Autuação", "")

    # local_processo = Jurisdição + Órgão julgador
    jurisdicao = campos_mapeados.get("Jurisdição", "")
    orgao = campos_mapeados.get("Órgão julgador", "")
    dados.local_processo = f"{jurisdicao} — {orgao}" if jurisdicao and orgao else jurisdicao or orgao

    # ── div#poloAtivo: Empresa + CNPJ + Advogado ──
    try:
        polo_ativo = driver.find_element(By.ID, "poloAtivo")
        partes = polo_ativo.find_elements(
            By.CSS_SELECTOR, "table.table tbody tr td > span > span"
        )

        for parte in partes:
            try:
                texto = parte.text.strip()
                if not texto:
                    continue

                # Extrair CNPJ
                cnpj_match = RE_CNPJ_TEXTO.search(texto)
                if cnpj_match:
                    dados.cnpj = cnpj_match.group(1)
                    # Empresa = tudo antes de " - CNPJ:"
                    nome_empresa = texto.split(" - CNPJ:")[0].strip()
                    dados.empresa = nome_empresa
                    logger.info(f"Empresa: {dados.empresa} | CNPJ: {dados.cnpj}")
                    break  # Primeiro com CNPJ é a empresa principal

            except Exception:
                continue

        # Se não encontrou CNPJ, usar o primeiro nome do polo ativo
        if not dados.empresa and partes:
            try:
                texto = partes[0].text.strip()
                # Remover qualificação (IMPETRANTE), (AUTOR), etc.
                nome = re.sub(r"\s*\([^)]+\)\s*$", "", texto).strip()
                dados.empresa = nome
            except Exception:
                pass

        # Advogado(s) no polo ativo
        try:
            advogados = polo_ativo.find_elements(
                By.CSS_SELECTOR, "ul.tree small.text-muted span"
            )
            for adv in advogados:
                try:
                    texto = adv.text.strip()
                    if texto and "ADVOGADO" in texto.upper():
                        # Extrair nome: "NOME COMPLETO registrado(a) civilmente como ... - CPF: ... (ADVOGADO)"
                        nome_adv = texto.split(" registrado(a)")[0].strip()
                        if not nome_adv or nome_adv == texto:
                            nome_adv = texto.split(" - CPF:")[0].strip()
                        dados.advogado = nome_adv
                        logger.info(f"Advogado: {dados.advogado}")
                        break
                except Exception:
                    continue
        except Exception:
            pass

    except NoSuchElementException:
        logger.warning("div#poloAtivo não encontrado")

    # ── Número do processo (da barra de topo, mais confiável) ──
    try:
        titulo = driver.find_element(
            By.CSS_SELECTOR, "a.titulo-topo.dropdown-toggle.titulo-topo-desktop"
        )
        titulo_text = titulo.text.strip()
        num_match = RE_NUMERO_PROCESSO.search(titulo_text)
        if num_match:
            processo["numero_processo"] = num_match.group()
    except Exception:
        pass

    # ── ID do processo para URLs de download ──
    id_proc = _extrair_id_processo_da_pagina(driver)
    if id_proc:
        processo["id_processo_pagina"] = id_proc

    # Fechar dropdown (clicar novamente no toggle)
    try:
        toggle = driver.find_element(
            By.CSS_SELECTOR, "a.titulo-topo.dropdown-toggle.titulo-topo-desktop"
        )
        driver.execute_script("arguments[0].click();", toggle)
        time.sleep(0.3)
    except Exception:
        pass

    return dados






# ============================================
# SEÇÃO 5: Documentos-alvo + Download PDF
# ============================================

def _normalizar_texto(texto: str) -> str:
    """Normaliza texto: lowercase, remove acentos, strip."""
    import unicodedata
    texto = texto.lower().strip()
    nfkd = unicodedata.normalize("NFKD", texto)
    return nfkd.encode("ascii", "ignore").decode("ascii")


def _aguardar_timeline_atualizar(driver, timeout: int = TIMEOUT_AJAX) -> None:
    """
    Aguarda a timeline atualizar após uma busca (smart wait).
    Checks only modalStatusContainer — the actual RichFaces loading spinner.
    """
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script(
                "var el = document.getElementById('modalStatusContainer');"
                "return !el || el.style.display === 'none' || el.style.display === '';"
            )
        )
    except TimeoutException:
        pass

    time.sleep(0.5)


def _aguardar_overlay_sumir(driver, timeout: int = 5) -> None:
    """
    Aguarda o loading indicator do RichFaces sumir (modalStatusContainer).
    Quick check — 5s max, not 15s. Only checks the actual loading spinner,
    not structural overlay divs that are always in the DOM.
    """
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script(
                "var el = document.getElementById('modalStatusContainer');"
                "return !el || el.style.display === 'none' || el.style.display === '';"
            )
        )
    except TimeoutException:
        pass  # Continue anyway — don't block the flow


def _buscar_na_timeline(driver, termo: str) -> bool:
    """
    Busca server-side na timeline. Retorna True se a busca foi executada com sucesso.
    Aguarda overlay sumir antes de clicar. Usa JS fallback se click real falhar.
    """
    try:
        # Aguardar overlay sumir antes de interagir
        _aguardar_overlay_sumir(driver)

        campo = driver.find_element(By.ID, "divTimeLine:txtPesquisa")
        driver.execute_script(
            "var el = arguments[0]; el.value = ''; el.value = arguments[1];",
            campo, termo,
        )
        time.sleep(0.2)

        btn = driver.find_element(By.ID, "divTimeLine:btnPesquisar")

        # Tentar click real, fallback para JS
        try:
            btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", btn)

        logger.info(f"Timeline: buscando '{termo}'")
        _aguardar_timeline_atualizar(driver)
        return True

    except Exception as e:
        logger.warning(f"Busca na timeline FALHOU para '{termo}': {e}")
        return False


def _limpar_busca_timeline(driver) -> None:
    """Limpa o campo de busca e restaura timeline completa."""
    try:
        _aguardar_overlay_sumir(driver)

        campo = driver.find_element(By.ID, "divTimeLine:txtPesquisa")
        driver.execute_script("arguments[0].value = '';", campo)
        time.sleep(0.2)

        btn = driver.find_element(By.ID, "divTimeLine:btnPesquisar")
        try:
            btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", btn)

        _aguardar_timeline_atualizar(driver)
    except Exception:
        pass


def _extrair_documentos_visiveis(driver) -> list[dict]:
    """
    Extrai todos os documentos atualmente visíveis na timeline.
    Retorna lista de dicts: {id_documento, nome_documento, texto_completo}
    """
    documentos = []
    ids_vistos = set()

    try:
        container = driver.find_element(By.ID, "divTimeLine:divEventosTimeLine")
        spans = container.find_elements(By.TAG_NAME, "span")

        spans_com_texto = 0
        spans_match_pattern = 0

        for span in spans:
            try:
                texto = span.text.strip()
                # Strip unicode whitespace (non-breaking spaces, zero-width chars)
                texto = re.sub(r'[\u00a0\u200b\u200c\u200d\ufeff]', ' ', texto).strip()

                if not texto:
                    continue
                spans_com_texto += 1

                match = RE_DOC_TIMELINE.search(texto)
                if not match:
                    continue
                spans_match_pattern += 1

                doc_id = match.group(1)
                doc_nome = match.group(2).strip()

                if doc_id in ids_vistos:
                    continue
                ids_vistos.add(doc_id)

                documentos.append({
                    "id_documento": doc_id,
                    "nome_documento": doc_nome,
                    "texto_completo": texto,
                })
            except StaleElementReferenceException:
                continue
            except Exception:
                continue

        logger.info(
            f"  Timeline: {len(spans)} spans, {spans_com_texto} com texto, "
            f"{spans_match_pattern} padrão doc, {len(documentos)} únicos"
        )

        # Diagnostic: if no docs matched, show what the spans actually contain
        if spans_match_pattern == 0 and spans_com_texto > 0:
            sample = []
            for span in spans:
                try:
                    t = span.text.strip()
                    if t and len(sample) < 3:
                        sample.append(repr(t[:80]))
                except Exception:
                    pass
            if sample:
                logger.info(f"  Amostra de textos não-match: {', '.join(sample)}")

    except Exception as e:
        logger.error(f"Erro ao extrair documentos visíveis: {e}")

    return documentos


def _carregar_registro_downloads() -> list[RegistroDownload]:
    """Carrega o registro de downloads existente (para deduplicação)."""
    csv_path = settings.REGISTRO_DOWNLOADS_CSV
    if not csv_path.exists():
        return []

    registros = []
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                try:
                    registros.append(RegistroDownload(
                        cnpj=row.get("cnpj", ""),
                        numero_processo=row.get("numero_processo", ""),
                        tipo_documento=TipoDocumento(row.get("tipo_documento", "")),
                        nome_documento=row.get("nome_documento", ""),
                        caminho_pdf=row.get("caminho_pdf", ""),
                        timestamp=row.get("timestamp", ""),
                    ))
                except Exception:
                    continue
    except Exception as e:
        logger.warning(f"Erro ao ler registro de downloads: {e}")

    return registros


def _salvar_registro_download(registro: RegistroDownload) -> None:
    """Adiciona uma linha ao registro de downloads (append)."""
    csv_path = settings.REGISTRO_DOWNLOADS_CSV
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    file_exists = csv_path.exists()
    fieldnames = ["cnpj", "numero_processo", "tipo_documento", "nome_documento", "caminho_pdf", "timestamp"]

    try:
        with open(csv_path, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
            if not file_exists:
                writer.writeheader()
            writer.writerow({
                "cnpj": registro.cnpj,
                "numero_processo": registro.numero_processo,
                "tipo_documento": registro.tipo_documento.value,
                "nome_documento": registro.nome_documento,
                "caminho_pdf": registro.caminho_pdf,
                "timestamp": registro.timestamp,
            })
    except Exception as e:
        logger.error(f"Erro ao salvar registro de download: {e}")


def _aguardar_download(diretorio: Path, timeout: int = 30, snapshot_antes: set = None) -> Optional[Path]:
    """Aguarda um novo arquivo aparecer no diretório de downloads."""
    if snapshot_antes is None:
        snapshot_antes = set(diretorio.glob("*"))

    inicio = time.time()
    while time.time() - inicio < timeout:
        em_progresso = list(diretorio.glob("*.crdownload")) + list(diretorio.glob("*.tmp"))

        agora = set(diretorio.glob("*"))
        novos = agora - snapshot_antes
        novos_reais = {
            f for f in novos
            if f.is_file()
            and f.suffix not in (".crdownload", ".tmp")
            and not f.name.startswith(".")
        }

        if novos_reais and not em_progresso:
            arquivo = max(novos_reais, key=lambda p: p.stat().st_mtime)
            logger.info(f"  Arquivo: {arquivo.name} ({arquivo.stat().st_size / 1024:.0f} KB)")
            return arquivo

        time.sleep(1)

    return None


def _baixar_documento_visivel(
    driver,
    doc_id: str,
    doc_nome: str,
    tipo_doc: TipoDocumento,
    num_proc: str,
    cnpj_digits: str,
    cnpj_dir: Path,
    forcar: bool = False,
) -> Optional[RegistroDownload]:
    """
    Baixa um documento que JÁ ESTÁ VISÍVEL na timeline (não re-busca).
    Exatamente como um humano: clica no doc → preview → botão download → confirm.

    PRECONDIÇÃO: o documento com doc_id já está no DOM da timeline.
    """
    num_proc_safe = num_proc.replace(".", "_").replace("-", "_")
    nome_arquivo = f"{cnpj_digits}_{num_proc_safe}_{tipo_doc.value}_{doc_id}.pdf"
    caminho_final = cnpj_dir / nome_arquivo

    if not forcar and caminho_final.exists() and caminho_final.stat().st_size > 0:
        logger.info(f"  Pulando (já existe): {caminho_final.name}")
        return None

    logger.info(f"  Baixando: {doc_id} - {doc_nome}")

    try:
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": str(cnpj_dir),
        })
    except Exception:
        pass

    # ── Clicar no documento → preview ──
    preview_carregou = False
    try:
        _aguardar_overlay_sumir(driver)

        container = driver.find_element(By.ID, "divTimeLine:divEventosTimeLine")
        spans = container.find_elements(By.TAG_NAME, "span")

        for span in spans:
            try:
                texto = re.sub(r'[\u00a0\u200b\u200c\u200d\ufeff]', ' ', span.text).strip()
                if doc_id in texto:
                    link = span.find_element(By.XPATH, "ancestor::a[1]")
                    try:
                        link.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", link)
                    preview_carregou = True
                    break
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"  Erro ao clicar documento: {e}")

    if not preview_carregou:
        logger.warning(f"  Não conseguiu clicar preview de {doc_id}")
        return None

    # ── Aguardar botão download ──
    try:
        _aguardar_overlay_sumir(driver)
        WebDriverWait(driver, TIMEOUT_ELEMENT).until(
            EC.element_to_be_clickable((By.ID, "detalheDocumento:download"))
        )
    except TimeoutException:
        logger.warning(f"  Botão de download não apareceu para {doc_id}")
        return None

    time.sleep(PAUSE_TIMELINE)

    # ── Snapshot + clicar download ──
    arquivos_antes = set(cnpj_dir.glob("*"))

    try:
        _aguardar_overlay_sumir(driver)
        btn = driver.find_element(By.ID, "detalheDocumento:download")
        try:
            btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", btn)
    except Exception as e:
        logger.error(f"  Erro botão download: {e}")
        return None

    # ── Aceitar confirm ──
    try:
        WebDriverWait(driver, TIMEOUT_AJAX).until(EC.alert_is_present())
        alert = driver.switch_to.alert
        alert.accept()
        logger.info(f"  Confirm aceito")
    except (TimeoutException, NoAlertPresentException):
        pass

    time.sleep(PAUSE_TIMELINE)

    # ── Aguardar download ──
    arquivo_baixado = _aguardar_download(cnpj_dir, timeout=30, snapshot_antes=arquivos_antes)

    if arquivo_baixado:
        if arquivo_baixado != caminho_final:
            try:
                arquivo_baixado.rename(caminho_final)
            except Exception:
                caminho_final = arquivo_baixado

        registro = RegistroDownload(
            cnpj=cnpj_digits,
            numero_processo=num_proc,
            tipo_documento=tipo_doc,
            nome_documento=doc_nome,
            caminho_pdf=str(caminho_final),
        )
        _salvar_registro_download(registro)
        logger.info(f"  ✓ {caminho_final.name}")
        return registro
    else:
        logger.warning(f"  Download não concluiu: {doc_id}")
        return None


def buscar_e_baixar_documentos(
    driver,
    processo: dict,
    cnpj: str,
    registros: list[RegistroDownload],
    forcar: bool = False,
) -> list[RegistroDownload]:
    """
    Busca e baixa documentos-alvo em UMA passagem por tipo.
    Para cada tipo: busca na timeline → encontra → baixa IMEDIATAMENTE
    enquanto os docs estão no DOM. Sem re-busca por doc_id.

    Fluxo:
      1. Buscar "decisão" → baixar cada DECISÃO
      2. (SENTENÇA comentada — projeto opera com PETIÇÃO e DECISÃO)
      3. Buscar "inicial" → baixar Petição inicial (por nome)
      4. Limpar busca
    """
    num_proc = processo["numero_processo"]
    cnpj_digits = _so_digitos(cnpj)
    cnpj_dir = settings.DATA_DOCUMENTOS_DIR / cnpj_digits
    cnpj_dir.mkdir(parents=True, exist_ok=True)

    downloads = []

    # ── DECISÃO ──
    try:
        if _buscar_na_timeline(driver, "decisão"):
            docs = _extrair_documentos_visiveis(driver)
            decisoes = [d for d in docs if _normalizar_texto(d["nome_documento"]).startswith("decisao")]
            logger.info(f"  DECISÃO: {len(decisoes)} documento(s) encontrado(s)")
            for doc in decisoes:
                logger.info(f"    → {doc['texto_completo']}")
                reg = _baixar_documento_visivel(
                    driver, doc["id_documento"], doc["nome_documento"],
                    TipoDocumento.DECISAO, num_proc, cnpj_digits, cnpj_dir, forcar,
                )
                if reg:
                    downloads.append(reg)
                    registros.append(reg)
        else:
            logger.warning(f"  Busca 'decisão' falhou para {num_proc}")
    except Exception as e:
        logger.error(f"  Erro no bloco DECISÃO para {num_proc}: {type(e).__name__}: {e}")

    # Limpar timeline antes de próxima busca (evita stale DOM entre blocos)
    _limpar_busca_timeline(driver)

    # ── SENTENÇA — comentado: projeto opera com PETIÇÃO e DECISÃO apenas ──
    # Para reativar, descomentar o bloco abaixo:
    # try:
    #     if _buscar_na_timeline(driver, "sentença"):
    #         docs = _extrair_documentos_visiveis(driver)
    #         sentencas = [d for d in docs if "sentenca" in _normalizar_texto(d["nome_documento"])]
    #         for doc in sentencas:
    #             reg = _baixar_documento_visivel(
    #                 driver, doc["id_documento"], doc["nome_documento"],
    #                 TipoDocumento.SENTENCA, num_proc, cnpj_digits, cnpj_dir, forcar,
    #             )
    #             if reg:
    #                 downloads.append(reg)
    #                 registros.append(reg)
    # except Exception as e:
    #     logger.error(f"  Erro no bloco SENTENÇA: {e}")

    # ── PETIÇÃO: buscar "inicial" → baixar por nome apenas ──
    try:
        if _buscar_na_timeline(driver, "inicial"):
            docs = _extrair_documentos_visiveis(driver)
            peticoes = [
                d for d in docs
                if (
                    _normalizar_texto(d["nome_documento"]).startswith("peticao inicial")
                    or _normalizar_texto(d["nome_documento"]).startswith("inicial")
                )
                and "emenda" not in _normalizar_texto(d["nome_documento"])
            ]
            logger.info(f"  PETIÇÃO: {len(peticoes)} documento(s) encontrado(s)")
            for doc in peticoes:
                logger.info(f"    → {doc['texto_completo']}")
                reg = _baixar_documento_visivel(
                    driver, doc["id_documento"], doc["nome_documento"],
                    TipoDocumento.PETICAO, num_proc, cnpj_digits, cnpj_dir, forcar,
                )
                if reg:
                    downloads.append(reg)
                    registros.append(reg)
        else:
            logger.warning(f"  Busca 'inicial' falhou para {num_proc}")
    except Exception as e:
        logger.error(f"  Erro no bloco PETIÇÃO para {num_proc}: {type(e).__name__}: {e}")

    # ── Limpar busca ──
    _limpar_busca_timeline(driver)

    logger.info(f"  Downloads neste processo: {len(downloads)}")
    return downloads

# SEÇÃO 6: Orquestrador
# ============================================

def processar_cnpj(
    driver,
    cnpj: str,
    aba_consulta: str,
    registros: list[RegistroDownload],
    forcar_download: bool = False,
) -> dict:
    """
    Processa um CNPJ completo: pesquisa, itera processos, extrai metadados,
    lista documentos e baixa PDFs.

    Args:
        driver: WebDriver autenticado
        cnpj: CNPJ a pesquisar
        aba_consulta: handle da aba de consulta
        registros: lista de RegistroDownload para deduplicação (atualizada in-place)
        forcar_download: se True, re-baixa PDFs já existentes

    Retorna:
        dict com:
            - cnpj: str
            - dados_empresa: DadosEmpresa (do primeiro processo)
            - processos: list[dict] (todos os processos com metadados)
            - downloads: list[RegistroDownload] (downloads realizados)
            - erros: list[str]
    """
    cnpj_formatado = _formatar_cnpj(cnpj)
    cnpj_digits = _so_digitos(cnpj)

    resultado = {
        "cnpj": cnpj_digits,
        "dados_empresa": DadosEmpresa(),
        "processos": [],
        "downloads": [],
        "erros": [],
    }

    logger.info(f"\n{'='*50}")
    logger.info(f"Processando CNPJ: {cnpj_formatado}")
    logger.info(f"{'='*50}")

    # ── Navegar para consulta ──
    driver.switch_to.window(aba_consulta)
    if not navegar_para_consulta(driver):
        resultado["erros"].append("Não foi possível carregar página de consulta")
        return resultado

    # ── Pesquisar CNPJ ──
    if not pesquisar_cnpj(driver, cnpj):
        logger.info(f"Nenhum processo encontrado para {cnpj_formatado}")
        return resultado

    # ── Iterar páginas de processos ──
    dados_empresa_coletado = False

    for pagina, processos_pagina in iterar_paginas_processos(driver):
        logger.info(f"Página {pagina}: {len(processos_pagina)} processos filtrados")

        for idx_proc, processo in enumerate(processos_pagina):
            # Verificar parada graciosa
            if _verificar_parada():
                logger.info("Parada graciosa — encerrando processamento deste CNPJ")
                return resultado

            num_proc = processo["numero_processo"]
            id_proc = processo["id_processo"]
            logger.info(f"[{idx_proc+1}/{len(processos_pagina)}] Processo {num_proc} (id={id_proc})")

            # Abrir processo
            aba_proc = abrir_processo(driver, processo, aba_consulta)
            if not aba_proc:
                resultado["erros"].append(f"Falha ao abrir processo {num_proc}")
                continue

            try:
                # ── Extrair metadados (fault-tolerant — não impede downloads) ──
                dados = DadosEmpresa()
                try:
                    dados = extrair_metadados_processo(driver, processo)
                    if not dados_empresa_coletado and dados.esta_completo():
                        resultado["dados_empresa"] = dados
                        dados_empresa_coletado = True
                        logger.info(f"Dados da empresa coletados: {dados.empresa}")
                except Exception as e_meta:
                    logger.warning(f"Metadados parciais para {num_proc}: {e_meta}")

                # ── Buscar e baixar documentos-alvo ──
                try:
                    docs_baixados = buscar_e_baixar_documentos(
                        driver, processo,
                        cnpj=cnpj,
                        registros=registros,
                        forcar=forcar_download,
                    )
                    resultado["downloads"].extend(docs_baixados)
                except Exception as e_doc:
                    logger.error(f"Erro nos downloads do processo {num_proc}: {e_doc}")
                    resultado["erros"].append(f"Erro downloads {num_proc}: {e_doc}")

            except Exception as e_proc:
                logger.error(f"Erro inesperado no processo {num_proc}: {e_proc}")
                resultado["erros"].append(f"Erro {num_proc}: {e_proc}")

            finally:
                # SEMPRE registrar processo (mesmo com erros parciais)
                processo["dados_empresa"] = dados
                resultado["processos"].append(processo)

                # SEMPRE fechar aba do processo e voltar para consulta
                fechar_aba_processo(driver, aba_proc, aba_consulta)
                time.sleep(PAUSE_BETWEEN_ACTIONS)

    # ── Resumo ──
    n_proc = len(resultado["processos"])
    n_down = len(resultado["downloads"])
    n_erros = len(resultado["erros"])
    logger.info(
        f"CNPJ {cnpj_formatado} concluído: "
        f"{n_proc} processos, {n_down} downloads, {n_erros} erros"
    )

    # ── Salvar dados da empresa em JSON (para a UI) ──
    try:
        import json as _json
        dados_emp = resultado.get("dados_empresa")
        if dados_emp and dados_emp.esta_completo():
            empresa_json = settings.DATA_DOCUMENTOS_DIR / cnpj_digits / "empresa.json"
            empresa_json.parent.mkdir(parents=True, exist_ok=True)
            empresa_json.write_text(
                _json.dumps(dados_emp.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(f"Dados empresa salvos: {empresa_json}")
    except Exception as e:
        logger.warning(f"Não foi possível salvar empresa.json: {e}")

    return resultado


def executar_downloads(
    cnpjs: list[str],
    forcar_download: bool = False,
) -> list[dict]:
    """
    Função principal: processa uma lista de CNPJs de ponta a ponta.

    Fluxo completo:
      1. Abrir Chrome com perfil de automação
      2. Aguardar login manual via whom.doc9
      3. Para cada CNPJ: pesquisar → filtrar → abrir processos → metadados → download
      4. Fechar Chrome

    Args:
        cnpjs: lista de CNPJs (com ou sem formatação)
        forcar_download: se True, re-baixa tudo (ignora dedup)

    Retorna:
        Lista de dicts (um por CNPJ) com resultados do processamento.
    """
    resultados = []

    # Garantir pastas existem
    settings.garantir_pastas()

    # Carregar registro de downloads para deduplicação
    registros = _carregar_registro_downloads()
    logger.info(f"Registro de downloads carregado: {len(registros)} entradas")

    # Remover flag de parada anterior se existir
    if STOP_FLAG_FILE.exists():
        STOP_FLAG_FILE.unlink()

    print("\n  [DICA] Para interromper a automação de forma segura:")
    print(f"     Crie o arquivo: touch {STOP_FLAG_FILE}")
    print("     A automação encerrará após o processo atual.\n")

    # Iniciar navegador
    driver = None
    try:
        driver = iniciar_navegador()

        # Aguardar autenticação
        if not aguardar_autenticacao(driver):
            logger.error("Autenticação não concluída — abortando")
            return resultados

        # Fechar popups iniciais
        fechar_popups(driver)
        time.sleep(PAUSE_BETWEEN_ACTIONS)

        # Aba de consulta (a aba principal após auth)
        aba_consulta = driver.current_window_handle

        # Processar cada CNPJ
        for i, cnpj in enumerate(cnpjs):
            logger.info(f"\n[{i+1}/{len(cnpjs)}] CNPJ: {_formatar_cnpj(cnpj)}")

            try:
                resultado = processar_cnpj(
                    driver, cnpj, aba_consulta, registros,
                    forcar_download=forcar_download,
                )
                resultados.append(resultado)
            except Exception as e:
                logger.error(f"Erro fatal no CNPJ {cnpj}: {e}")
                resultados.append({
                    "cnpj": _so_digitos(cnpj),
                    "dados_empresa": DadosEmpresa(),
                    "processos": [],
                    "downloads": [],
                    "erros": [str(e)],
                })

            # Pausa entre CNPJs
            if i < len(cnpjs) - 1:
                # Verificar parada graciosa
                if _verificar_parada():
                    logger.info("Parada graciosa — encerrando execução")
                    break

                logger.info(
                    f"Pausa de {settings.PAUSE_BETWEEN_CNPJS_SECONDS}s antes do próximo CNPJ..."
                )
                time.sleep(settings.PAUSE_BETWEEN_CNPJS_SECONDS)

    except Exception as e:
        logger.error(f"Erro fatal na execução: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Manter navegador aberto — navegar de volta para consulta
        if driver:
            try:
                navegar_para_consulta(driver)
                logger.info("Chrome mantido aberto na página de consulta")
            except Exception:
                try:
                    driver.quit()
                    logger.info("Chrome fechado (fallback)")
                except Exception:
                    pass
            driver = None

    # ── Resumo final ──
    total_proc = sum(len(r["processos"]) for r in resultados)
    total_down = sum(len(r["downloads"]) for r in resultados)
    total_erros = sum(len(r["erros"]) for r in resultados)
    logger.info(f"\n{'='*50}")
    logger.info(f"EXECUÇÃO CONCLUÍDA")
    logger.info(f"  CNPJs processados : {len(resultados)}")
    logger.info(f"  Processos         : {total_proc}")
    logger.info(f"  Downloads         : {total_down}")
    logger.info(f"  Erros             : {total_erros}")
    logger.info(f"{'='*50}")

    return resultados