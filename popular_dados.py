import multiprocessing as mp
import random
import time
import psycopg2
from psycopg2.extras import execute_values
import trabalho

ALVO_MB = 750
QUANTIDADE_PROCESSOS = 4
TAMANHO_LOTE = 400
TOTAL_USUARIOS = 3000
CHECAR_VOLUME_A_CADA_LOTES = 10

ATIVOS = [
    ("BTC", "Bitcoin", 350000.00),
    ("ETH", "Ethereum", 18000.00),
    ("SOL", "Solana", 820.00),
    ("PETR4", "Petrobras PN", 38.00),
    ("VALE3", "Vale ON", 62.00),
]

def conectar():
    return psycopg2.connect(**trabalho.bd_configuracoes)


def formatar_mb(bytes_total):
    return bytes_total / 1024 / 1024


def consultar_totais():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        """
        SELECT
            pg_database_size(current_database()),
            (SELECT COUNT(*) FROM ordens),
            (SELECT COUNT(*) FROM trades)
        """
    )
    resultado = cursor.fetchone()

    cursor.close()
    conexao.close()
    return resultado


def preparar_dados_iniciais():
    conexao = conectar()
    cursor = conexao.cursor()

    execute_values(
        cursor,
        """
        INSERT INTO ativos (id, nome, eh_moeda_cotacao)
        VALUES %s
        ON CONFLICT (id) DO NOTHING
        """,
        [(codigo, nome, False) for codigo, nome, _ in ATIVOS],
    )

    cursor.execute(
        """
        INSERT INTO usuarios (nome)
        SELECT 'Trader ' || gs
        FROM generate_series(1, %s) AS gs
        WHERE NOT EXISTS (
            SELECT 1 FROM usuarios u WHERE u.nome = 'Trader ' || gs
        )
        """,
        (TOTAL_USUARIOS,),
    )

    cursor.execute(
        """
        SELECT id
        FROM usuarios
        WHERE nome LIKE 'Trader %'
        ORDER BY id
        LIMIT %s
        """,
        (TOTAL_USUARIOS,),
    )
    usuarios = [linha[0] for linha in cursor.fetchall()]

    carteiras = []
    for usuario_id in usuarios:
        carteiras.append((usuario_id, "BRL", "1000000000.00000000", "0.00000000"))

        for codigo, _, _ in ATIVOS:
            carteiras.append((usuario_id, codigo, "100000.00000000", "0.00000000"))

    execute_values(
        cursor,
        """
        INSERT INTO carteiras (
            usuario_id,
            ativo_id,
            saldo_disponivel,
            saldo_bloqueado
        )
        VALUES %s
        ON CONFLICT (usuario_id, ativo_id) DO NOTHING
        """,
        carteiras,
        page_size=5000,
    )

    conexao.commit()
    cursor.close()
    conexao.close()

    return usuarios


def atualizar_preco(preco_atual, preco_inicial):
    variacao = random.uniform(-0.004, 0.004)
    novo_preco = preco_atual * (1 + variacao)

    if novo_preco < preco_inicial * 0.50:
        novo_preco = preco_inicial * 0.50

    if novo_preco > preco_inicial * 1.50:
        novo_preco = preco_inicial * 1.50

    return novo_preco


def gerar_ordens(usuarios, precos):
    ordens = []

    for _ in range(TAMANHO_LOTE):
        ativo, _, preco_inicial = random.choice(ATIVOS)
        preco_atual = atualizar_preco(precos[ativo], preco_inicial)
        precos[ativo] = preco_atual

        tipo = random.choice(["BID", "ASK"])

        if tipo == "BID":
            preco_ordem = preco_atual * random.uniform(0.998, 1.003)
        else:
            preco_ordem = preco_atual * random.uniform(0.997, 1.002)

        valor_ordem = random.uniform(100.00, 10000.00)
        quantidade = valor_ordem / preco_ordem

        ordens.append(
            (
                random.choice(usuarios),
                ativo,
                tipo,
                f"{preco_ordem:.8f}",
                f"{quantidade:.8f}",
            )
        )

    return ordens


def trabalhador(numero, parar, fila, usuarios, alvo_bytes):
    conexao = conectar()
    cursor = conexao.cursor()
    total_inserido = 0
    lotes = 0

    precos = {codigo: preco for codigo, _, preco in ATIVOS}
    random.seed(time.time() + numero)

    while not parar.is_set():
        ordens = gerar_ordens(usuarios, precos)

        execute_values(
            cursor,
            """
            INSERT INTO ordens (
                usuario_id,
                ativo_base_id,
                tipo,
                preco,
                quantidade_total
            )
            VALUES %s
            """,
            ordens,
            page_size=TAMANHO_LOTE,
        )

        conexao.commit()
        total_inserido += len(ordens)
        lotes += 1

        if lotes % CHECAR_VOLUME_A_CADA_LOTES == 0:
            cursor.execute("SELECT pg_database_size(current_database())")
            tamanho_atual = cursor.fetchone()[0]

            if tamanho_atual >= alvo_bytes:
                parar.set()

    cursor.close()
    conexao.close()
    fila.put(total_inserido)


def popular_banco():
    trabalho.criar_tabelas()

    alvo_bytes = ALVO_MB * 1024 * 1024
    usuarios = preparar_dados_iniciais()

    inicio = time.time()
    parar = mp.Event()
    fila = mp.Queue()
    processos = []

    for numero in range(QUANTIDADE_PROCESSOS):
        processo = mp.Process(
            target=trabalhador,
            args=(numero, parar, fila, usuarios, alvo_bytes),
        )
        processo.start()
        processos.append(processo)

    for processo in processos:
        processo.join()

    tempo_total = time.time() - inicio
    tamanho_banco, total_ordens, total_trades = consultar_totais()

    ordens_geradas = 0
    while not fila.empty():
        ordens_geradas += fila.get()

    print(f"Volume total inserido: {formatar_mb(tamanho_banco):.2f} MB")
    print(f"Ordens inseridas nesta execucao: {ordens_geradas}")
    print(f"Ordens no banco: {total_ordens}")
    print(f"Trades criados: {total_trades}")
    print(f"Tempo de execucao: {tempo_total:.2f} segundos")


if __name__ == "__main__":
    mp.freeze_support()
    popular_banco()
