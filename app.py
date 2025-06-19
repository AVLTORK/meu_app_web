from flask import Flask, render_template, request, redirect, url_for, session, send_file
import sqlite3
import csv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import time

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta'
DB_PATH = 'mensagens.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
# ------------------- Páginas Estáticas do Front -------------------
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


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario']
        senha = request.form['senha']
        if usuario == 'admin' and senha == '1234':
            session['logado'] = True
            return redirect(url_for('admin'))
        else:
            return 'Login inválido'
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logado', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/enviar', methods=['POST'])
def enviar():
    nome = request.form['nome']
    mensagem = request.form['mensagem']
    conn = get_db_connection()
    conn.execute('INSERT INTO mensagens (nome, mensagem) VALUES (?, ?)', (nome, mensagem))
    conn.commit()
    conn.close()
    enviar_whatsapp(nome, mensagem)
    return redirect(url_for('index'))

@app.route('/admin')
def admin():
    if not session.get('logado'):
        return redirect(url_for('login'))

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

@app.route('/excluir/<int:id>')
def excluir(id):
    if not session.get('logado'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM mensagens WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    if not session.get('logado'):
        return redirect(url_for('login'))

    conn = get_db_connection()
    if request.method == 'POST':
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

@app.route('/exportar')
def exportar():
    if not session.get('logado'):
        return redirect(url_for('login'))

    conn = get_db_connection()
    mensagens = conn.execute('SELECT * FROM mensagens').fetchall()
    conn.close()

    with open('mensagens.csv', 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['ID', 'Nome', 'Mensagem'])
        for m in mensagens:
            writer.writerow([m['id'], m['nome'], m['mensagem']])

    return send_file('mensagens.csv', as_attachment=True)

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

        botao = driver.find_element(By.XPATH, '//span[@data-icon="send"]')
        botao.click()
        time.sleep(5)
        driver.quit()
    except Exception as e:
        print(f"Erro ao enviar WhatsApp: {e}")

if __name__ == '__main__':
    app.run(debug=True)
