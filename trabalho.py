import psycopg2
from psycopg2 import Error

# Configurações de conexão
bd_configuracoes = {
    "host": "localhost",
    "database": "banco_trabalho",
    "user": "postgres",
    "password": "minhasenha",
    "port": "5433"
}

# Lista de comandos organizados por ordem de dependência
queryParaSubirBanco = [
    """
    CREATE TABLE IF NOT EXISTS usuarios (
        id BIGSERIAL PRIMARY KEY,
        nome VARCHAR(100) NOT NULL,
        criado_em TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ativos (
        id VARCHAR(10) PRIMARY KEY,
        nome VARCHAR(100) NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS carteiras (
        usuario_id BIGINT REFERENCES usuarios(id),
        ativo_id VARCHAR(10) REFERENCES ativos(id),
        saldo_disponivel NUMERIC(24, 8) NOT NULL DEFAULT 0.00000000 CHECK (saldo_disponivel >= 0),
        saldo_bloqueado NUMERIC(24, 8) NOT NULL DEFAULT 0.00000000 CHECK (saldo_bloqueado >= 0),
        PRIMARY KEY (usuario_id, ativo_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ordens (
        id BIGSERIAL PRIMARY KEY,
        usuario_id BIGINT REFERENCES usuarios(id),
        ativo_base_id VARCHAR(10) REFERENCES ativos(id),
        tipo VARCHAR(4) CHECK (tipo IN ('BID', 'ASK')),
        preco NUMERIC(24, 8) NOT NULL,
        quantidade_total NUMERIC(24, 8) NOT NULL,
        quantidade_preenchida NUMERIC(24, 8) NOT NULL DEFAULT 0,
        status VARCHAR(15) NOT NULL,
        criado_em TIMESTAMP(6) NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS trades (
        id BIGSERIAL PRIMARY KEY,
        ordem_maker_id BIGINT REFERENCES ordens(id),
        preco_executado NUMERIC(24, 8) NOT NULL,
        quantidade_executada NUMERIC(24, 8) NOT NULL,
        executado_em TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS auditoria_ordens (
        id BIGSERIAL PRIMARY KEY,
        ordem_id BIGINT REFERENCES ordens(id),
        status_anterior VARCHAR(15),
        status_novo VARCHAR(15) NOT NULL,
        modificado_em TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS candles_ohlcv (
        ativo_base_id VARCHAR(10) REFERENCES ativos(id),
        minuto TIMESTAMP NOT NULL,
        open NUMERIC(24, 8) NOT NULL,
        high NUMERIC(24, 8) NOT NULL,
        low NUMERIC(24, 8) NOT NULL,
        close NUMERIC(24, 8) NOT NULL,
        volume NUMERIC(24, 8) NOT NULL DEFAULT 0,
        PRIMARY KEY (ativo_base_id, minuto)
    ) PARTITION BY RANGE (minuto);
    """
]

def criar_tabelas():
    connection = None
    try:
        # Conectando ao banco de dados
        print("Conectando ao PostgreSQL...")
        connection = psycopg2.connect(**bd_configuracoes)
        cursor = connection.cursor()

        # Executando cada query 
        for query in queryParaSubirBanco:
            cursor.execute(query)
            
        # Commit das alterações
        connection.commit()
        print("Tabelas criadas com sucesso! A estrutura ER está pronta.")

        # Criando uma partição de exemplo para os candles do mês de Junho
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS candles_ohlcv_2026_06 
            PARTITION OF candles_ohlcv 
            FOR VALUES FROM ('2026-06-01 00:00:00') TO ('2026-07-01 00:00:00');
        """)
        connection.commit()
        print("Partição inicial da tabela candles_ohlcv criada.")

    except Error as e:
        print(f"Erro ao conectar ou executar script no PostgreSQL: {e}")
        if connection:
            connection.rollback()
            
    finally:
        # Fechando a conexão
        if connection:
            cursor.close()
            connection.close()
            print("Conexão com o PostgreSQL encerrada.")

if __name__ == "__main__":
    criar_tabelas()