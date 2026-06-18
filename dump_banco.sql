DROP TABLE IF EXISTS candles_ohlcv CASCADE;
DROP TABLE IF EXISTS auditoria_ordens CASCADE;
DROP TABLE IF EXISTS trades CASCADE;
DROP TABLE IF EXISTS ordens CASCADE;
DROP TABLE IF EXISTS carteiras CASCADE;
DROP TABLE IF EXISTS ativos CASCADE;
DROP TABLE IF EXISTS usuarios CASCADE;

CREATE TABLE usuarios (
    id BIGSERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ativos (
    id VARCHAR(10) PRIMARY KEY,
    nome VARCHAR(100) NOT NULL
);

CREATE TABLE carteiras (
    usuario_id BIGINT NOT NULL REFERENCES usuarios(id),
    ativo_id VARCHAR(10) NOT NULL REFERENCES ativos(id),
    saldo_disponivel NUMERIC(24, 8) NOT NULL DEFAULT 0,
    saldo_bloqueado NUMERIC(24, 8) NOT NULL DEFAULT 0,
    PRIMARY KEY (usuario_id, ativo_id),
    CHECK (saldo_disponivel >= 0),
    CHECK (saldo_bloqueado >= 0)
);

CREATE TABLE ordens (
    id BIGSERIAL PRIMARY KEY,
    usuario_id BIGINT NOT NULL REFERENCES usuarios(id),
    ativo_base_id VARCHAR(10) NOT NULL REFERENCES ativos(id),
    tipo VARCHAR(4) NOT NULL CHECK (tipo IN ('BID', 'ASK')),
    preco NUMERIC(24, 8) NOT NULL CHECK (preco > 0),
    quantidade_total NUMERIC(24, 8) NOT NULL CHECK (quantidade_total > 0),
    quantidade_preenchida NUMERIC(24, 8) NOT NULL DEFAULT 0,
    status VARCHAR(15) NOT NULL DEFAULT 'aberta'
        CHECK (status IN ('aberta', 'parcial', 'executada', 'cancelada')),
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE trades (
    id BIGSERIAL PRIMARY KEY,
    ordem_compra_id BIGINT NOT NULL REFERENCES ordens(id),
    ordem_venda_id BIGINT NOT NULL REFERENCES ordens(id),
    comprador_id BIGINT NOT NULL REFERENCES usuarios(id),
    vendedor_id BIGINT NOT NULL REFERENCES usuarios(id),
    ativo_base_id VARCHAR(10) NOT NULL REFERENCES ativos(id),
    preco NUMERIC(24, 8) NOT NULL,
    quantidade NUMERIC(24, 8) NOT NULL,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE auditoria_ordens (
    id BIGSERIAL PRIMARY KEY,
    ordem_id BIGINT NOT NULL REFERENCES ordens(id),
    status_anterior VARCHAR(15),
    status_novo VARCHAR(15) NOT NULL,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE candles_ohlcv (
    ativo_base_id VARCHAR(10) NOT NULL REFERENCES ativos(id),
    minuto TIMESTAMP NOT NULL,
    open NUMERIC(24, 8) NOT NULL,
    high NUMERIC(24, 8) NOT NULL,
    low NUMERIC(24, 8) NOT NULL,
    close NUMERIC(24, 8) NOT NULL,
    volume NUMERIC(24, 8) NOT NULL DEFAULT 0,
    PRIMARY KEY (ativo_base_id, minuto)
) PARTITION BY RANGE (minuto);

CREATE TABLE candles_ohlcv_2026
PARTITION OF candles_ohlcv
FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE TABLE candles_ohlcv_default
PARTITION OF candles_ohlcv DEFAULT;

INSERT INTO ativos (id, nome) VALUES
('BRL', 'Real'),
('BTC', 'Bitcoin'),
('ETH', 'Ethereum'),
('SOL', 'Solana'),
('PETR4', 'Petrobras PN'),
('VALE3', 'Vale ON');

CREATE INDEX idx_ordens_bid
ON ordens (ativo_base_id, preco DESC, criado_em)
WHERE tipo = 'BID' AND status IN ('aberta', 'parcial');

CREATE INDEX idx_ordens_ask
ON ordens (ativo_base_id, preco, criado_em)
WHERE tipo = 'ASK' AND status IN ('aberta', 'parcial');

CREATE OR REPLACE FUNCTION reservar_saldo()
RETURNS TRIGGER AS $$
BEGIN
    NEW.status := 'aberta';
    NEW.quantidade_preenchida := 0;

    IF NEW.tipo = 'BID' THEN
        UPDATE carteiras
        SET saldo_disponivel = saldo_disponivel - (NEW.preco * NEW.quantidade_total),
            saldo_bloqueado = saldo_bloqueado + (NEW.preco * NEW.quantidade_total)
        WHERE usuario_id = NEW.usuario_id
          AND ativo_id = 'BRL'
          AND saldo_disponivel >= (NEW.preco * NEW.quantidade_total);
    ELSE
        UPDATE carteiras
        SET saldo_disponivel = saldo_disponivel - NEW.quantidade_total,
            saldo_bloqueado = saldo_bloqueado + NEW.quantidade_total
        WHERE usuario_id = NEW.usuario_id
          AND ativo_id = NEW.ativo_base_id
          AND saldo_disponivel >= NEW.quantidade_total;
    END IF;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Saldo insuficiente';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION auditar_ordem()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO auditoria_ordens (ordem_id, status_anterior, status_novo)
        VALUES (NEW.id, NULL, NEW.status);
    ELSIF OLD.status <> NEW.status THEN
        INSERT INTO auditoria_ordens (ordem_id, status_anterior, status_novo)
        VALUES (NEW.id, OLD.status, NEW.status);
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION bloquear_trade()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Trades nao podem ser alterados ou apagados';
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION atualizar_candle()
RETURNS TRIGGER AS $$
DECLARE
    minuto_trade TIMESTAMP;
BEGIN
    minuto_trade := date_trunc('minute', NEW.criado_em);

    INSERT INTO candles_ohlcv (ativo_base_id, minuto, open, high, low, close, volume)
    VALUES (
        NEW.ativo_base_id,
        minuto_trade,
        NEW.preco,
        NEW.preco,
        NEW.preco,
        NEW.preco,
        NEW.quantidade
    )
    ON CONFLICT (ativo_base_id, minuto) DO UPDATE
    SET high = GREATEST(candles_ohlcv.high, EXCLUDED.high),
        low = LEAST(candles_ohlcv.low, EXCLUDED.low),
        close = EXCLUDED.close,
        volume = candles_ohlcv.volume + EXCLUDED.volume;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION executar_matching()
RETURNS TRIGGER AS $$
DECLARE
    entrada ordens%ROWTYPE;
    oposta ordens%ROWTYPE;
    qtd NUMERIC(24, 8);
    restante NUMERIC(24, 8);
    valor NUMERIC(24, 8);
    comprador BIGINT;
    vendedor BIGINT;
    ordem_compra BIGINT;
    ordem_venda BIGINT;
BEGIN
    SELECT * INTO entrada
    FROM ordens
    WHERE id = NEW.id
    FOR UPDATE;

    restante := entrada.quantidade_total - entrada.quantidade_preenchida;

    WHILE restante > 0 LOOP
        IF entrada.tipo = 'BID' THEN
            SELECT * INTO oposta
            FROM ordens
            WHERE ativo_base_id = entrada.ativo_base_id
              AND tipo = 'ASK'
              AND status IN ('aberta', 'parcial')
              AND quantidade_total > quantidade_preenchida
              AND preco <= entrada.preco
              AND id <> entrada.id
            ORDER BY preco, criado_em
            LIMIT 1
            FOR UPDATE SKIP LOCKED;
        ELSE
            SELECT * INTO oposta
            FROM ordens
            WHERE ativo_base_id = entrada.ativo_base_id
              AND tipo = 'BID'
              AND status IN ('aberta', 'parcial')
              AND quantidade_total > quantidade_preenchida
              AND preco >= entrada.preco
              AND id <> entrada.id
            ORDER BY preco DESC, criado_em
            LIMIT 1
            FOR UPDATE SKIP LOCKED;
        END IF;

        EXIT WHEN NOT FOUND;

        qtd := LEAST(restante, oposta.quantidade_total - oposta.quantidade_preenchida);
        valor := qtd * oposta.preco;

        IF entrada.tipo = 'BID' THEN
            comprador := entrada.usuario_id;
            vendedor := oposta.usuario_id;
            ordem_compra := entrada.id;
            ordem_venda := oposta.id;

            UPDATE carteiras
            SET saldo_bloqueado = saldo_bloqueado - (entrada.preco * qtd),
                saldo_disponivel = saldo_disponivel + ((entrada.preco - oposta.preco) * qtd)
            WHERE usuario_id = comprador AND ativo_id = 'BRL';
        ELSE
            comprador := oposta.usuario_id;
            vendedor := entrada.usuario_id;
            ordem_compra := oposta.id;
            ordem_venda := entrada.id;

            UPDATE carteiras
            SET saldo_bloqueado = saldo_bloqueado - valor
            WHERE usuario_id = comprador AND ativo_id = 'BRL';
        END IF;

        UPDATE carteiras
        SET saldo_bloqueado = saldo_bloqueado - qtd
        WHERE usuario_id = vendedor AND ativo_id = entrada.ativo_base_id;

        INSERT INTO carteiras (usuario_id, ativo_id, saldo_disponivel)
        VALUES (comprador, entrada.ativo_base_id, qtd)
        ON CONFLICT (usuario_id, ativo_id) DO UPDATE
        SET saldo_disponivel = carteiras.saldo_disponivel + EXCLUDED.saldo_disponivel;

        INSERT INTO carteiras (usuario_id, ativo_id, saldo_disponivel)
        VALUES (vendedor, 'BRL', valor)
        ON CONFLICT (usuario_id, ativo_id) DO UPDATE
        SET saldo_disponivel = carteiras.saldo_disponivel + EXCLUDED.saldo_disponivel;

        UPDATE ordens
        SET quantidade_preenchida = quantidade_preenchida + qtd,
            status = CASE
                WHEN quantidade_preenchida + qtd >= quantidade_total THEN 'executada'
                ELSE 'parcial'
            END
        WHERE id = oposta.id;

        restante := restante - qtd;

        UPDATE ordens
        SET quantidade_preenchida = quantidade_total - restante,
            status = CASE
                WHEN restante = 0 THEN 'executada'
                ELSE 'parcial'
            END
        WHERE id = entrada.id;

        INSERT INTO trades (
            ordem_compra_id,
            ordem_venda_id,
            comprador_id,
            vendedor_id,
            ativo_base_id,
            preco,
            quantidade
        )
        VALUES (
            ordem_compra,
            ordem_venda,
            comprador,
            vendedor,
            entrada.ativo_base_id,
            oposta.preco,
            qtd
        );
    END LOOP;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_best_orders(p_ativo_id VARCHAR, p_limite INTEGER DEFAULT 5)
RETURNS TABLE (tipo VARCHAR, preco NUMERIC, quantidade NUMERIC) AS $$
BEGIN
    RETURN QUERY
    SELECT o.tipo, o.preco, SUM(o.quantidade_total - o.quantidade_preenchida)
    FROM ordens o
    WHERE o.ativo_base_id = p_ativo_id
      AND o.tipo = 'BID'
      AND o.status IN ('aberta', 'parcial')
    GROUP BY o.tipo, o.preco
    ORDER BY o.preco DESC
    LIMIT p_limite;

    RETURN QUERY
    SELECT o.tipo, o.preco, SUM(o.quantidade_total - o.quantidade_preenchida)
    FROM ordens o
    WHERE o.ativo_base_id = p_ativo_id
      AND o.tipo = 'ASK'
      AND o.status IN ('aberta', 'parcial')
    GROUP BY o.tipo, o.preco
    ORDER BY o.preco
    LIMIT p_limite;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION cancel_order(p_ordem_id BIGINT)
RETURNS BOOLEAN AS $$
DECLARE
    ordem ordens%ROWTYPE;
    restante NUMERIC(24, 8);
BEGIN
    SELECT * INTO ordem
    FROM ordens
    WHERE id = p_ordem_id
    FOR UPDATE;

    IF NOT FOUND OR ordem.status NOT IN ('aberta', 'parcial') THEN
        RETURN FALSE;
    END IF;

    restante := ordem.quantidade_total - ordem.quantidade_preenchida;

    IF ordem.tipo = 'BID' THEN
        UPDATE carteiras
        SET saldo_disponivel = saldo_disponivel + (ordem.preco * restante),
            saldo_bloqueado = saldo_bloqueado - (ordem.preco * restante)
        WHERE usuario_id = ordem.usuario_id AND ativo_id = 'BRL';
    ELSE
        UPDATE carteiras
        SET saldo_disponivel = saldo_disponivel + restante,
            saldo_bloqueado = saldo_bloqueado - restante
        WHERE usuario_id = ordem.usuario_id AND ativo_id = ordem.ativo_base_id;
    END IF;

    UPDATE ordens
    SET status = 'cancelada'
    WHERE id = p_ordem_id;

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION user_portfolio(p_usuario_id BIGINT)
RETURNS TABLE (
    ativo_id VARCHAR,
    saldo_disponivel NUMERIC,
    saldo_bloqueado NUMERIC,
    saldo_total NUMERIC,
    ultimo_preco NUMERIC,
    valor_total_brl NUMERIC
) AS $$
    SELECT
        c.ativo_id,
        c.saldo_disponivel,
        c.saldo_bloqueado,
        c.saldo_disponivel + c.saldo_bloqueado,
        CASE
            WHEN c.ativo_id = 'BRL' THEN 1
            ELSE COALESCE((
                SELECT t.preco
                FROM trades t
                WHERE t.ativo_base_id = c.ativo_id
                ORDER BY t.criado_em DESC, t.id DESC
                LIMIT 1
            ), 0)
        END,
        (c.saldo_disponivel + c.saldo_bloqueado) *
        CASE
            WHEN c.ativo_id = 'BRL' THEN 1
            ELSE COALESCE((
                SELECT t.preco
                FROM trades t
                WHERE t.ativo_base_id = c.ativo_id
                ORDER BY t.criado_em DESC, t.id DESC
                LIMIT 1
            ), 0)
        END
    FROM carteiras c
    WHERE c.usuario_id = p_usuario_id;
$$ LANGUAGE SQL;

CREATE VIEW view_market_summary AS
SELECT
    a.id AS ativo_id,
    (
        SELECT t.preco
        FROM trades t
        WHERE t.ativo_base_id = a.id
        ORDER BY t.criado_em DESC, t.id DESC
        LIMIT 1
    ) AS ultimo_preco,
    (
        SELECT COALESCE(SUM(t.quantidade), 0)
        FROM trades t
        WHERE t.ativo_base_id = a.id
          AND t.criado_em >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
    ) AS volume_24h,
    (
        SELECT MAX(o.preco)
        FROM ordens o
        WHERE o.ativo_base_id = a.id
          AND o.tipo = 'BID'
          AND o.status IN ('aberta', 'parcial')
    ) AS melhor_bid,
    (
        SELECT MIN(o.preco)
        FROM ordens o
        WHERE o.ativo_base_id = a.id
          AND o.tipo = 'ASK'
          AND o.status IN ('aberta', 'parcial')
    ) AS melhor_ask,
    (
        SELECT ROUND(
            (
                MAX(t.preco) - MIN(t.preco)
            ) / NULLIF(MIN(t.preco), 0) * 100,
            4
        )
        FROM trades t
        WHERE t.ativo_base_id = a.id
          AND t.criado_em >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
    ) AS variacao_24h
FROM ativos a
WHERE a.id <> 'BRL';

CREATE VIEW view_trades_history AS
SELECT
    id,
    ativo_base_id,
    preco,
    quantidade,
    preco * quantidade AS valor_total,
    criado_em
FROM trades
ORDER BY criado_em DESC, id DESC;

CREATE VIEW view_traders_ranking AS
WITH movimentacao AS (
    SELECT comprador_id AS usuario_id, preco * quantidade AS volume
    FROM trades
    WHERE criado_em >= CURRENT_TIMESTAMP - INTERVAL '24 hours'

    UNION ALL

    SELECT vendedor_id AS usuario_id, preco * quantidade AS volume
    FROM trades
    WHERE criado_em >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
),
totais AS (
    SELECT usuario_id, SUM(volume) AS volume_24h
    FROM movimentacao
    GROUP BY usuario_id
)
SELECT
    RANK() OVER (ORDER BY t.volume_24h DESC) AS posicao,
    u.id AS usuario_id,
    u.nome,
    t.volume_24h
FROM totais t
JOIN usuarios u ON u.id = t.usuario_id;

CREATE TRIGGER trg_auditar_ordem
AFTER INSERT OR UPDATE OF status ON ordens
FOR EACH ROW
EXECUTE FUNCTION auditar_ordem();

CREATE TRIGGER trg_reservar_saldo
BEFORE INSERT ON ordens
FOR EACH ROW
EXECUTE FUNCTION reservar_saldo();

CREATE TRIGGER trg_matching
AFTER INSERT ON ordens
FOR EACH ROW
EXECUTE FUNCTION executar_matching();

CREATE TRIGGER trg_trade_bloqueado
BEFORE UPDATE OR DELETE ON trades
FOR EACH ROW
EXECUTE FUNCTION bloquear_trade();

CREATE TRIGGER trg_candle
AFTER INSERT ON trades
FOR EACH ROW
EXECUTE FUNCTION atualizar_candle();
