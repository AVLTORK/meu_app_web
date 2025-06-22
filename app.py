from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import os, sqlite3, secrets, csv, time, zipfile, requests
from werkzeug.utils import secure_filename
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "minha_chave_secreta_troque_depois")

DB_PATH = "mensagens.db"
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

MODO_DESENVOLVIMENTO = True
USERS = {"Lucia": "1234"}

# ---------- Google Drive ----------
CREDENTIALS_FILE = '0e0beecf-f561-49d0-9dd8-737faf57234c.json'
TOKEN_FILE = 'token.json'
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_drive_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

def create_drive_folder(folder_name, service):
    folder_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    folder = service.files().create(body=folder_metadata, fields='id').execute()
    return folder.get('id')

def upload_file_to_drive(file_storage, folder_id, service):
    if not file_storage or file_storage.filename == '':
        return None
    filename = secure_filename(file_storage.filename)
    temp_path = os.path.join(UPLOAD_FOLDER, filename)
    file_storage.save(temp_path)

    file_metadata = {'name': filename, 'parents': [folder_id]}
    media = MediaFileUpload(temp_path, resumable=False)
    uploaded = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()

    file_id = uploaded.get('id')
    web_link = uploaded.get('webViewLink')

    service.permissions().create(
        fileId=file_id,
        body={'role': 'reader', 'type': 'anyone'}
    ).execute()

    os.remove(temp_path)
    return web_link

# ---------- Banco de Dados ----------
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def criar_tabela_clientes():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
      CREATE TABLE IF NOT EXISTS clientes(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          nome TEXT,
          telefone TEXT,
          placa TEXT,
          endereco TEXT,
          email TEXT,
          foto_placa TEXT,
          foto_dianteira TEXT,
          foto_traseira TEXT,
          foto_lado_esq TEXT,
          foto_lado_dir TEXT,
          foto_dano TEXT,
          pasta_drive TEXT
      );
    """)
    conn.commit()
    conn.close()
criar_tabela_clientes()

def allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def salvar_imagem(file_storage):
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed(file_storage.filename):
        return None
    nome_seguro = secure_filename(file_storage.filename)
    unique = secrets.token_hex(4)
    _, ext = os.path.splitext(nome_seguro)
    final_name = f"{unique}{ext.lower()}"
    caminho = os.path.join(UPLOAD_FOLDER, final_name)
    file_storage.save(caminho)
    return final_name
# ---------- Autenticação ----------
@app.before_request
def proteger_rotas():
    if MODO_DESENVOLVIMENTO:
        return
    rotas_livres = ("/login", "/static/")
    if not session.get("user") and not request.path.startswith(rotas_livres):
        return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if MODO_DESENVOLVIMENTO:
        session["user"] = "dev"
        return redirect(url_for("home"))
    msg = ""
    if request.method == "POST":
        u, p = request.form["user"], request.form["pwd"]
        if USERS.get(u) == p:
            session["user"] = u
            return redirect(url_for("home"))
        msg = "Usuário ou senha inválidos"
    return render_template("login.html", msg=msg)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------- Páginas Base ----------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/rastreamento")
def rastreamento():
    return render_template("rastreamento.html")

@app.route("/bloqueio")
def bloqueio():
    return render_template("bloqueio.html")

@app.route("/consulta")
def consulta():
    return render_template("consulta.html")

@app.route("/orcamento")
def orcamento():
    return render_template("orcamento.html")
# ---------- Lista com Filtro e Paginação ----------
@app.route("/clientes")
def clientes():
    busca = request.args.get("busca", "")
    pagina = int(request.args.get("pagina", 1))
    por_pagina = 10
    offset = (pagina - 1) * por_pagina

    conn = get_db_connection()

    total = conn.execute("""
        SELECT COUNT(*) FROM clientes
        WHERE nome LIKE ? OR placa LIKE ?
    """, (f"%{busca}%", f"%{busca}%")).fetchone()[0]

    lista = conn.execute("""
        SELECT * FROM clientes
        WHERE nome LIKE ? OR placa LIKE ?
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """, (f"%{busca}%", f"%{busca}%", por_pagina, offset)).fetchall()
    conn.close()

    total_paginas = (total // por_pagina) + (1 if total % por_pagina > 0 else 0)

    return render_template("clientes.html", clientes=lista, busca=busca, pagina=pagina, total_paginas=total_paginas)
# ---------- Novo Cliente ----------
@app.route("/clientes/novo", methods=["GET", "POST"])
def novo_cliente():
    if request.method == "POST":
        dados = {k: request.form.get(k) for k in ("nome", "telefone", "placa", "endereco", "email")}

        # Google Drive → cria pasta com o nome do cliente
        service = get_drive_service()
        folder_id = create_drive_folder(dados["nome"], service)

        fotos_links = {}
        for campo in ("foto_placa", "foto_dianteira", "foto_traseira", "foto_lado_esq", "foto_lado_dir", "foto_dano"):
            file = request.files.get(campo)
            link = upload_file_to_drive(file, folder_id, service) if file else None
            fotos_links[campo] = link

        conn = get_db_connection()
        conn.execute("""
            INSERT INTO clientes
            (nome, telefone, placa, endereco, email,
             foto_placa, foto_dianteira, foto_traseira,
             foto_lado_esq, foto_lado_dir, foto_dano, pasta_drive)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            dados["nome"], dados["telefone"], dados["placa"], dados["endereco"], dados["email"],
            fotos_links["foto_placa"], fotos_links["foto_dianteira"], fotos_links["foto_traseira"],
            fotos_links["foto_lado_esq"], fotos_links["foto_lado_dir"], fotos_links["foto_dano"], folder_id
        ))
        conn.commit()
        conn.close()
        flash("Cliente cadastrado com sucesso!", "success")
        return redirect(url_for("clientes"))

    return render_template("novo_cliente.html")
# ---------- Editar Cliente ----------
@app.route("/clientes/editar/<int:id>", methods=["GET", "POST"])
def editar_cliente(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes WHERE id=?", (id,))
    cliente_atual = cursor.fetchone()

    if request.method == "POST":
        dados = {k: request.form.get(k) for k in ("nome", "telefone", "placa", "endereco", "email")}
        service = get_drive_service()
        folder_id = create_drive_folder(dados["nome"], service)

        fotos = {}
        for campo in ("foto_placa", "foto_dianteira", "foto_traseira", "foto_lado_esq", "foto_lado_dir", "foto_dano"):
            file = request.files.get(campo)
            if file and file.filename != "":
                link = upload_file_to_drive(file, folder_id, service)
                fotos[campo] = link
            else:
                fotos[campo] = cliente_atual[campo]

        cursor.execute("""
            UPDATE clientes
               SET nome=?, telefone=?, placa=?, endereco=?, email=?,
                   foto_placa=?, foto_dianteira=?, foto_traseira=?,
                   foto_lado_esq=?, foto_lado_dir=?, foto_dano=?, pasta_drive=?
             WHERE id=?
        """, (
            dados["nome"], dados["telefone"], dados["placa"], dados["endereco"], dados["email"],
            fotos["foto_placa"], fotos["foto_dianteira"], fotos["foto_traseira"],
            fotos["foto_lado_esq"], fotos["foto_lado_dir"], fotos["foto_dano"], folder_id, id
        ))
        conn.commit()
        conn.close()
        flash("Cliente atualizado com sucesso!", "success")
        return redirect(url_for("clientes"))

    conn.close()
    return render_template("editar_cliente.html", cliente=cliente_atual)
# ---------- Excluir Cliente ----------
@app.route("/clientes/excluir/<int:id>")
def excluir_cliente(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM clientes WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash("Cliente removido com sucesso.", "info")
    return redirect(url_for("clientes"))
# ---------- Visualizar Cliente ----------
@app.route("/clientes/<int:id>")
def visualizar_cliente(id):
    conn = get_db_connection()
    cliente = conn.execute("SELECT * FROM clientes WHERE id=?", (id,)).fetchone()
    conn.close()

    if not cliente:
        flash("Cliente não encontrado.", "warning")
        return redirect(url_for("clientes"))

    return render_template("visualizar_cliente.html", cliente=cliente)
# ---------- Exportar CSV Geral ----------
@app.route("/clientes/exportar")
def exportar_clientes():
    conn = get_db_connection()
    clientes = conn.execute("SELECT * FROM clientes ORDER BY id DESC").fetchall()
    conn.close()

    caminho_csv = "clientes_export.csv"
    with open(caminho_csv, mode="w", newline="", encoding="utf-8") as arquivo:
        writer = csv.writer(arquivo)
        writer.writerow([
            "ID", "Nome", "Telefone", "Placa", "Endereço", "Email",
            "Foto Placa", "Foto Dianteira", "Foto Traseira",
            "Foto Lado Esq", "Foto Lado Dir", "Foto Dano"
        ])
        for c in clientes:
            writer.writerow([
                c["id"], c["nome"], c["telefone"], c["placa"], c["endereco"], c["email"],
                c["foto_placa"], c["foto_dianteira"], c["foto_traseira"],
                c["foto_lado_esq"], c["foto_lado_dir"], c["foto_dano"]
            ])
    return send_file(caminho_csv, as_attachment=True)
# ---------- Exportar PDF de Todos ----------
@app.route("/clientes/exportar_pdf_todos")
def exportar_todos_clientes_pdf():
    conn = get_db_connection()
    clientes = conn.execute("SELECT * FROM clientes ORDER BY id DESC").fetchall()
    conn.close()

    caminho_pdf = "clientes_lista.pdf"
    c = canvas.Canvas(caminho_pdf, pagesize=letter)
    c.setFont("Helvetica", 11)
    largura, altura = letter
    y = altura - 40

    for cliente in clientes:
        c.drawString(50, y, f"ID: {cliente['id']} – Nome: {cliente['nome']}")
        y -= 16
        c.drawString(60, y, f"Telefone: {cliente['telefone']}")
        y -= 16
        c.drawString(60, y, f"Placa: {cliente['placa']}")
        y -= 16
        c.drawString(60, y, f"E-mail: {cliente['email']}")
        y -= 20
        if y < 80:
            c.showPage()
            y = altura - 40

    c.save()
    return send_file(caminho_pdf, as_attachment=True)
# ---------- Exportar Fotos ZIP ----------
@app.route("/clientes/exportar_zip/<int:id>")
def exportar_fotos_zip(id):
    conn = get_db_connection()
    cliente = conn.execute("SELECT * FROM clientes WHERE id=?", (id,)).fetchone()
    conn.close()

    if not cliente:
        flash("Cliente não encontrado.", "warning")
        return redirect(url_for("clientes"))

    temp_folder = "temp_downloads"
    os.makedirs(temp_folder, exist_ok=True)

    zip_path = os.path.join(temp_folder, f"cliente_{id}_fotos.zip")

    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for campo, label in {
            'foto_placa':'placa',
            'foto_dianteira':'dianteira',
            'foto_traseira':'traseira',
            'foto_lado_esq':'lado_esq',
            'foto_lado_dir':'lado_dir',
            'foto_dano':'dano'
        }.items():
            link = cliente[campo]
            if link:
                try:
                    response = requests.get(link)
                    if response.status_code == 200:
                        ext = ".jpg"
                        nome_arquivo = f"{label}{ext}"
                        caminho_temp = os.path.join(temp_folder, nome_arquivo)
                        with open(caminho_temp, 'wb') as f:
                            f.write(response.content)
                        zipf.write(caminho_temp, nome_arquivo)
                        os.remove(caminho_temp)
                except Exception as e:
                    print(f"Erro ao baixar imagem {label}: {e}")

    return send_file(zip_path, as_attachment=True)
# ---------- WhatsApp Rápido ----------
@app.route("/clientes/whatsapp/<int:id>")
def enviar_whatsapp_cliente(id):
    conn = get_db_connection()
    cliente = conn.execute("SELECT * FROM clientes WHERE id=?", (id,)).fetchone()
    conn.close()

    if not cliente:
        flash("Cliente não encontrado.", "warning")
        return redirect(url_for("clientes"))

    telefone = cliente['telefone']
    texto = f"Olá {cliente['nome']}, sua ficha está disponível na Oficina SMHITE."

    numero_destino = "55" + telefone.strip().replace(" ", "").replace("-", "")

    try:
        service = Service('chromedriver.exe')
        options = webdriver.ChromeOptions()
        options.add_argument(r"--user-data-dir=selenium")
        driver = webdriver.Chrome(service=service, options=options)

        driver.get(f"https://web.whatsapp.com/send?phone={numero_destino}&text={texto.replace(' ', '%20')}")
        time.sleep(15)
        botao = driver.find_element(By.XPATH, '//span[@data-icon="send"]')
        botao.click()
        time.sleep(5)
        driver.quit()
        flash("Mensagem enviada via WhatsApp!", "success")
    except Exception as e:
        print(f"Erro WhatsApp: {e}")
        flash(f"Erro ao enviar WhatsApp: {e}", "danger")

    return redirect(url_for("visualizar_cliente", id=id))
# ---------- WhatsApp Personalizado ----------
@app.route("/clientes/whatsapp_personalizado/<int:id>", methods=["GET", "POST"])
def whatsapp_personalizado(id):
    conn = get_db_connection()
    cliente = conn.execute("SELECT * FROM clientes WHERE id=?", (id,)).fetchone()
    conn.close()

    if not cliente:
        flash("Cliente não encontrado.", "warning")
        return redirect(url_for("clientes"))

    if request.method == "POST":
        mensagem = request.form.get("mensagem")
        telefone = cliente["telefone"]
        numero_destino = "55" + telefone.strip().replace(" ", "").replace("-", "")

        try:
            service = Service('chromedriver.exe')
            options = webdriver.ChromeOptions()
            options.add_argument(r"--user-data-dir=selenium")
            driver = webdriver.Chrome(service=service, options=options)

            texto_url = mensagem.replace(" ", "%20").replace("\n", "%0A")
            driver.get(f"https://web.whatsapp.com/send?phone={numero_destino}&text={texto_url}")
            time.sleep(15)

            botao = driver.find_element(By.XPATH, '//span[@data-icon="send"]')
            botao.click()
            time.sleep(5)
            driver.quit()

            flash("WhatsApp enviado com sucesso!", "success")
        except Exception as e:
            print(f"Erro WhatsApp personalizado: {e}")
            flash(f"Erro ao enviar WhatsApp: {e}", "danger")

        return redirect(url_for("visualizar_cliente", id=id))

    return render_template("whatsapp_personalizado.html", cliente=cliente)
# ---------- Exportação CSV Filtrado ----------
@app.route("/clientes/exportar_csv_filtrado")
def exportar_clientes_filtrados():
    busca = request.args.get("busca", "")

    conn = get_db_connection()
    clientes = conn.execute("""
        SELECT * FROM clientes
        WHERE nome LIKE ? OR placa LIKE ?
        ORDER BY id DESC
    """, (f"%{busca}%", f"%{busca}%")).fetchall()
    conn.close()

    caminho_csv = "clientes_filtrados.csv"
    with open(caminho_csv, mode="w", newline="", encoding="utf-8") as arquivo:
        writer = csv.writer(arquivo)
        writer.writerow([
            "ID", "Nome", "Telefone", "Placa", "Endereço", "Email",
            "Foto Placa", "Foto Dianteira", "Foto Traseira",
            "Foto Lado Esq", "Foto Lado Dir", "Foto Dano"
        ])
        for c in clientes:
            writer.writerow([
                c["id"], c["nome"], c["telefone"], c["placa"], c["endereco"], c["email"],
                c["foto_placa"], c["foto_dianteira"], c["foto_traseira"],
                c["foto_lado_esq"], c["foto_lado_dir"], c["foto_dano"]
            ])

    return send_file(caminho_csv, as_attachment=True)
# ---------- Exportação PDF Filtrado ----------
@app.route("/clientes/exportar_pdf_filtrado")
def exportar_clientes_pdf_filtrado():
    busca = request.args.get("busca", "")

    conn = get_db_connection()
    clientes = conn.execute("""
        SELECT * FROM clientes
        WHERE nome LIKE ? OR placa LIKE ?
        ORDER BY id DESC
    """, (f"%{busca}%", f"%{busca}%")).fetchall()
    conn.close()

    if not clientes:
        flash("Nenhum cliente encontrado no filtro.", "warning")
        return redirect(url_for("clientes"))

    caminho_pdf = "clientes_filtrados.pdf"
    c = canvas.Canvas(caminho_pdf, pagesize=letter)
    c.setFont("Helvetica", 11)
    largura, altura = letter
    y = altura - 40

    for cliente in clientes:
        c.drawString(50, y, f"ID: {cliente['id']} – Nome: {cliente['nome']}")
        y -= 16
        c.drawString(60, y, f"Telefone: {cliente['telefone']}")
        y -= 16
        c.drawString(60, y, f"Placa: {cliente['placa']}")
        y -= 16
        c.drawString(60, y, f"E-mail: {cliente['email']}")
        y -= 20
        if y < 80:
            c.showPage()
            y = altura - 40

    c.save()
    return send_file(caminho_pdf, as_attachment=True)
# ---------- Relatórios ----------
@app.route("/clientes/relatorios")
def relatorios_clientes():
    conn = get_db_connection()

    total_clientes = conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
    total_com_placa = conn.execute("""
        SELECT COUNT(*) FROM clientes WHERE placa IS NOT NULL AND placa != ''
    """).fetchone()[0]
    total_com_email = conn.execute("""
        SELECT COUNT(*) FROM clientes WHERE email IS NOT NULL AND email != ''
    """).fetchone()[0]
    total_fotos = conn.execute("""
        SELECT COUNT(*) FROM clientes
        WHERE foto_placa IS NOT NULL OR foto_dianteira IS NOT NULL OR foto_traseira IS NOT NULL
        OR foto_lado_esq IS NOT NULL OR foto_lado_dir IS NOT NULL OR foto_dano IS NOT NULL
    """).fetchone()[0]

    conn.close()

    return render_template("relatorios_clientes.html",
        total_clientes=total_clientes,
        total_com_placa=total_com_placa,
        total_com_email=total_com_email,
        total_fotos=total_fotos
    )
# ---------- Run ----------
if __name__ == "__main__":
    app.run(debug=True)


