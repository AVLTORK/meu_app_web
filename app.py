from flask import Flask, render_template, request, redirect, url_for, session, send_file
import os
import sqlite3
import csv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import time

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "minha_chave_secreta_troque_depois")  # Chave de sessão

DB_PATH = 'mensagens.db'
USERS = {"Lucia": "1234"}  # Usuário e senha temporários

# Proteção de todas as rotas (exceto login e static)
@app.before_request
def proteger_todas_as_rotas():
    rotas_livres = ("/login", "/static/")
    if not session.get("user") and not request.path.startswith(rotas_livres):
        return redirect(url_for("login"))

# Rota de login
@app.route("/login", methods=["GET", "POST"])
def login():
    msg = ""
    if request.method == "POST":
        usuario = request.form["user"]
        senha = request.form["pwd"]
        if USERS.get(usuario) == senha:
            session["user"] = usuario
            return redirect(url_for("home"))
        msg = "Usuário ou senha inválidos"
    return render_template("login.html", msg=msg)

# Logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# Conexão com banco
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Página principal
@app.route("/")
def home():
    return render_template("index.html")

# Demais páginas protegidas
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

@app.route("/admin")
def admin():
    busca = request.args.get('busca', '')
    pagina = int(request.args.get('pagina', 1))
    por_pagina = 5
    offset = (pagina - 1) * por_pagina

    conn = get_db_connection()
    total = conn.execute('SELECT COUNT(*) FROM mensagens WHERE nome LIKE ? OR mensagem LIKE ?', 
                         (f'%{busca}%', f'%{busca}%')).fetchone()[0]
    mensagens = conn.execute('''
        SELECT * FROM mensagens WHERE nome LIKE ? OR mensagem LIKE ?
        ORDER BY id DESC LIMIT ? OFFSET ?
    ''', (f'%{busca}%', f'%{busca}%', por_pagina, offset)).fetchall()
    conn.close()

    total_paginas = (total // por_pagina) + (1 if total % por_pagina > 0 else 0)

    return render_template('admin.html', mensagens=mensagens, busca=busca, pagina=pagina, total_paginas=total_paginas)

@app.route("/enviar", methods=["POST"])
def enviar():
    nome = request.form['nome']
    mensagem = request.form['mensagem']
    conn = get_db_connection()
    conn.execute('INSERT INTO mensagens (nome, mensagem) VALUES (?, ?)', (nome, mensagem))
    conn.commit()
    conn.close()
    enviar_whatsapp(nome, mensagem)
    return redirect(url_for('home'))

@app.route("/excluir/<int:id>")
def excluir(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM mensagens WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route("/editar/<int:id>", methods=["GET", "POST"])
def editar(id):
    conn = get_db_connection()
    if request.method == "POST":
        novo_nome = request.form['nome']
        nova_msg = request.form['mensagem']
        conn.execute('UPDATE mensagens SET nome = ?, mensagem = ? WHERE id = ?', (novo_nome, nova_msg, id))
        conn.commit()
        conn.close()
        return redirect(url_for('admin'))
    else:
        msg = conn.execute('SELECT * FROM mensagens WHERE id = ?', (id,)).fetchone()
        conn.close()
        return render_template('editar.html', msg=msg)

@app.route("/exportar")
def exportar():
    conn = get_db_connection()
    mensagens = conn.execute('SELECT * FROM mensagens').fetchall()
    conn.close()

    with open('mensagens.csv', 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['ID', 'Nome', 'Mensagem'])
        for m in mensagens:
            writer.writerow([m['id'], m['nome'], m['mensagem']])

    return send_file('mensagens.csv', as_attachment=True)

# Função WhatsApp
def enviar_whatsapp(nome, mensagem):
    try:
        chrome_service = Service('chromedriver.exe')
        options = webdriver.ChromeOptions()
        options.add_argument(r"--user-data-dir=selenium")
        driver = webdriver.Chrome(service=chrome_service, options=options)

        driver.get('https://web.whatsapp.com')
        time.sleep(10)

        numero_destino = '55996135546'
        texto = f"Nova mensagem recebida:\nNome: {nome}\nMensagem: {mensagem}"
        texto = texto.replace(' ', '%20').replace('\n', '%0A')
        driver.get(f'https://web.whatsapp.com/send?phone={numero_destino}&text={texto}')
        time.sleep(10)

        botao = driver.find_element(By.XPATH, '//span[@data-icon=\"send\"]')
        botao.click()
        time.sleep(5)
        driver.quit()
    except Exception as e:
        print(f"Erro ao enviar WhatsApp: {e}")

if __name__ == '__main__':
    app.run(debug=True)
