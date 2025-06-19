import sqlite3

conn = sqlite3.connect('mensagens.db')
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS mensagens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    mensagem TEXT NOT NULL
)
""")
conn.commit()
conn.close()
print("Banco de dados e tabela criados com sucesso!")
