import psycopg2


bd_configuracoes = {
    "host": "localhost",
    "database": "banco_trabalho",
    "user": "postgres",
    "password": "minhasenha",
    "port": "5433",
}


def criar_tabelas():
    conexao = psycopg2.connect(**bd_configuracoes)
    cursor = conexao.cursor()

    with open("dump_banco.sql", "r", encoding="utf-8") as arquivo:
        cursor.execute(arquivo.read())

    conexao.commit()
    cursor.close()
    conexao.close()
    print("Banco criado com sucesso.")


if __name__ == "__main__":
    criar_tabelas()
