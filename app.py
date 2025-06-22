"""
app.py — Flask + Firebase Realtime Database
Coloque serviceAccountKey.json na raiz do projeto.
"""

from flask import Flask, render_template, request, redirect, url_for
import firebase_admin
from firebase_admin import credentials, db

# ─────────── Inicializa Firebase ───────────
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")  # arquivo da service-account
    firebase_admin.initialize_app(cred, {
        "databaseURL": "https://appweb-82f31-default-rtdb.firebaseio.com/"  # ajuste se seu URL for diferente
    })

app = Flask(__name__)

# ─────────── Funções Firebase (CRUD) ───────────
def listar_clientes_firebase():
    ref = db.reference("/clientes")
    data = ref.get()
    if data:
        return [{**v, "id": k} for k, v in data.items()]
    return []

def adicionar_cliente_firebase(nome, telefone, placa, email):
    ref = db.reference("/clientes")
    ref.push({
        "nome": nome,
        "telefone": telefone,
        "placa": placa,
        "email": email
    })

def buscar_cliente_firebase(cliente_id):
    ref = db.reference(f"/clientes/{cliente_id}")
    data = ref.get()
    if data:
        data["id"] = cliente_id
        return data
    return None

# ─────────── Rotas Flask ───────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/clientes")
def clientes():
    busca = request.args.get("busca", "")
    clientes = listar_clientes_firebase()
    if busca:
        clientes = [c for c in clientes
                    if busca.lower() in c["nome"].lower()
                    or busca.lower() in c["placa"].lower()]
    return render_template("clientes.html", clientes=clientes, busca=busca)

@app.route("/clientes/<cliente_id>")
def visualizar_cliente(cliente_id):
    cliente = buscar_cliente_firebase(cliente_id)
    if not cliente:
        return "<h1>Cliente não encontrado</h1>", 404
    return (
        f"<h1>Cliente: {cliente['nome']}</h1>"
        f"<p>Telefone: {cliente['telefone']}<br>"
        f"Placa: {cliente['placa']}<br>"
        f"E-mail: {cliente['email']}</p>"
    )

@app.route("/clientes/novo", methods=["GET", "POST"])
def novo_cliente():
    if request.method == "POST":
        nome = request.form.get("nome")
        telefone = request.form.get("telefone")
        placa = request.form.get("placa")
        email = request.form.get("email")
        adicionar_cliente_firebase(nome, telefone, placa, email)
        return redirect(url_for("clientes"))
    return render_template("novo_cliente.html")

# ─────────── Run ───────────
if __name__ == "__main__":
    app.run(debug=True)
