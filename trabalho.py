import psycopg2
from psycopg2 import Error

bd_configuracoes = {
    "host": "localhost",
    "database": "banco_trabalho",
    "user": "postgres",
    "password": "minhasenha",
    "port": "5433",
}

queryParaSubirBanco = [
    """
    CREATE TABLE IF NOT EXISTS usuarios (
        id BIGSERIAL PRIMARY KEY,
        nome VARCHAR(100) NOT NULL,
        criado_em TIMESTAMP(6) NOT NULL DEFAULT clock_timestamp()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ativos (
        id VARCHAR(10) PRIMARY KEY,
        nome VARCHAR(100) NOT NULL,
        eh_moeda_cotacao BOOLEAN NOT NULL DEFAULT FALSE
    );
    """,
    """
    ALTER TABLE ativos
    ADD COLUMN IF NOT EXISTS eh_moeda_cotacao BOOLEAN NOT NULL DEFAULT FALSE;
    """,
    """
    INSERT INTO ativos (id, nome, eh_moeda_cotacao)
    VALUES ('BRL', 'Real Brasileiro', TRUE)
    ON CONFLICT (id) DO UPDATE
    SET nome = EXCLUDED.nome,
        eh_moeda_cotacao = EXCLUDED.eh_moeda_cotacao;
    """,
    """
    CREATE TABLE IF NOT EXISTS carteiras (
        usuario_id BIGINT NOT NULL REFERENCES usuarios(id),
        ativo_id VARCHAR(10) NOT NULL REFERENCES ativos(id),
        saldo_disponivel NUMERIC(30, 8) NOT NULL DEFAULT 0.00000000,
        saldo_bloqueado NUMERIC(30, 8) NOT NULL DEFAULT 0.00000000,
        PRIMARY KEY (usuario_id, ativo_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ordens (
        id BIGSERIAL PRIMARY KEY,
        usuario_id BIGINT NOT NULL REFERENCES usuarios(id),
        ativo_base_id VARCHAR(10) NOT NULL REFERENCES ativos(id),
        tipo VARCHAR(4) NOT NULL,
        preco NUMERIC(24, 8) NOT NULL,
        quantidade_total NUMERIC(24, 8) NOT NULL,
        quantidade_preenchida NUMERIC(24, 8) NOT NULL DEFAULT 0.00000000,
        status VARCHAR(15) NOT NULL DEFAULT 'aberta',
        criado_em TIMESTAMP(6) NOT NULL DEFAULT clock_timestamp()
    );
    """,
    """
    ALTER TABLE ordens
    ALTER COLUMN status SET DEFAULT 'aberta';
    """,
    """
    CREATE TABLE IF NOT EXISTS trades (
        id BIGSERIAL PRIMARY KEY,
        ordem_maker_id BIGINT REFERENCES ordens(id),
        ordem_taker_id BIGINT REFERENCES ordens(id),
        comprador_id BIGINT REFERENCES usuarios(id),
        vendedor_id BIGINT REFERENCES usuarios(id),
        ativo_base_id VARCHAR(10) REFERENCES ativos(id),
        preco_executado NUMERIC(24, 8) NOT NULL,
        quantidade_executada NUMERIC(24, 8) NOT NULL,
        valor_executado NUMERIC(30, 8),
        executado_em TIMESTAMP(6) NOT NULL DEFAULT clock_timestamp()
    );
    """,
    """
    ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS ordem_taker_id BIGINT REFERENCES ordens(id),
    ADD COLUMN IF NOT EXISTS comprador_id BIGINT REFERENCES usuarios(id),
    ADD COLUMN IF NOT EXISTS vendedor_id BIGINT REFERENCES usuarios(id),
    ADD COLUMN IF NOT EXISTS ativo_base_id VARCHAR(10) REFERENCES ativos(id),
    ADD COLUMN IF NOT EXISTS valor_executado NUMERIC(30, 8);
    """,
    """
    CREATE TABLE IF NOT EXISTS auditoria_ordens (
        id BIGSERIAL PRIMARY KEY,
        ordem_id BIGINT NOT NULL REFERENCES ordens(id),
        status_anterior VARCHAR(15),
        status_novo VARCHAR(15) NOT NULL,
        modificado_em TIMESTAMP(6) NOT NULL DEFAULT clock_timestamp()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS candles_ohlcv (
        ativo_base_id VARCHAR(10) NOT NULL REFERENCES ativos(id),
        minuto TIMESTAMP(0) NOT NULL,
        open NUMERIC(24, 8) NOT NULL,
        high NUMERIC(24, 8) NOT NULL,
        low NUMERIC(24, 8) NOT NULL,
        close NUMERIC(24, 8) NOT NULL,
        volume NUMERIC(30, 8) NOT NULL DEFAULT 0.00000000,
        PRIMARY KEY (ativo_base_id, minuto)
    ) PARTITION BY RANGE (minuto);
    """,
    """
    CREATE TABLE IF NOT EXISTS candles_ohlcv_2026_06
    PARTITION OF candles_ohlcv
    FOR VALUES FROM ('2026-06-01 00:00:00') TO ('2026-07-01 00:00:00');
    """,
    """
    CREATE TABLE IF NOT EXISTS candles_ohlcv_default
    PARTITION OF candles_ohlcv DEFAULT;
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'carteiras_saldos_nao_negativos'
        ) THEN
            ALTER TABLE carteiras
            ADD CONSTRAINT carteiras_saldos_nao_negativos
            CHECK (saldo_disponivel >= 0 AND saldo_bloqueado >= 0);
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ordens_tipo_check'
        ) THEN
            ALTER TABLE ordens
            ADD CONSTRAINT ordens_tipo_check CHECK (tipo IN ('BID', 'ASK'));
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ordens_status_check'
        ) THEN
            ALTER TABLE ordens
            ADD CONSTRAINT ordens_status_check
            CHECK (status IN ('aberta', 'parcial', 'executada', 'cancelada'));
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ordens_preco_positivo'
        ) THEN
            ALTER TABLE ordens
            ADD CONSTRAINT ordens_preco_positivo CHECK (preco > 0);
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ordens_quantidade_valida'
        ) THEN
            ALTER TABLE ordens
            ADD CONSTRAINT ordens_quantidade_valida
            CHECK (
                quantidade_total > 0
                AND quantidade_preenchida >= 0
                AND quantidade_preenchida <= quantidade_total
            );
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'trades_valores_positivos'
        ) THEN
            ALTER TABLE trades
            ADD CONSTRAINT trades_valores_positivos
            CHECK (
                preco_executado > 0
                AND quantidade_executada > 0
                AND (valor_executado IS NULL OR valor_executado > 0)
            );
        END IF;
    END $$;
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_carteiras_ativo
    ON carteiras (ativo_id, usuario_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ordens_bid_book
    ON ordens (ativo_base_id, preco DESC, criado_em ASC, id ASC)
    WHERE tipo = 'BID' AND status IN ('aberta', 'parcial');
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ordens_ask_book
    ON ordens (ativo_base_id, preco ASC, criado_em ASC, id ASC)
    WHERE tipo = 'ASK' AND status IN ('aberta', 'parcial');
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_trades_ativo_tempo
    ON trades (ativo_base_id, executado_em DESC, id DESC);
    """,
    """
    CREATE OR REPLACE FUNCTION preparar_ordem_insert()
    RETURNS TRIGGER AS $$
    DECLARE
        v_ativo_reter VARCHAR(10);
        v_valor_reter NUMERIC(30, 8);
    BEGIN
        IF NEW.tipo NOT IN ('BID', 'ASK') THEN
            RAISE EXCEPTION 'Tipo de ordem invalido: %', NEW.tipo;
        END IF;

        IF NEW.preco <= 0 OR NEW.quantidade_total <= 0 THEN
            RAISE EXCEPTION 'Preco e quantidade precisam ser positivos';
        END IF;

        NEW.quantidade_preenchida := 0.00000000;
        NEW.status := COALESCE(NULLIF(NEW.status, ''), 'aberta');

        IF NEW.status <> 'aberta' THEN
            RAISE EXCEPTION 'Toda ordem nova deve entrar com status aberta';
        END IF;

        IF NEW.tipo = 'BID' THEN
            v_ativo_reter := 'BRL';
            v_valor_reter := NEW.preco * NEW.quantidade_total;
        ELSE
            v_ativo_reter := NEW.ativo_base_id;
            v_valor_reter := NEW.quantidade_total;
        END IF;

        UPDATE carteiras
        SET saldo_disponivel = saldo_disponivel - v_valor_reter,
            saldo_bloqueado = saldo_bloqueado + v_valor_reter
        WHERE usuario_id = NEW.usuario_id
          AND ativo_id = v_ativo_reter
          AND saldo_disponivel >= v_valor_reter;

        IF NOT FOUND THEN
            RAISE EXCEPTION
                'Saldo insuficiente para usuario %, ativo %, valor %',
                NEW.usuario_id,
                v_ativo_reter,
                v_valor_reter;
        END IF;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """,
    """
    CREATE OR REPLACE FUNCTION auditar_status_ordem()
    RETURNS TRIGGER AS $$
    BEGIN
        IF TG_OP = 'INSERT' THEN
            INSERT INTO auditoria_ordens (ordem_id, status_anterior, status_novo)
            VALUES (NEW.id, NULL, NEW.status);
            RETURN NEW;
        END IF;

        IF OLD.status IS DISTINCT FROM NEW.status THEN
            INSERT INTO auditoria_ordens (ordem_id, status_anterior, status_novo)
            VALUES (NEW.id, OLD.status, NEW.status);
        END IF;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """,
    """
    CREATE OR REPLACE FUNCTION atualizar_candle_trade()
    RETURNS TRIGGER AS $$
    DECLARE
        v_minuto TIMESTAMP(0);
    BEGIN
        v_minuto := date_trunc('minute', NEW.executado_em);

        INSERT INTO candles_ohlcv (
            ativo_base_id,
            minuto,
            open,
            high,
            low,
            close,
            volume
        )
        VALUES (
            NEW.ativo_base_id,
            v_minuto,
            NEW.preco_executado,
            NEW.preco_executado,
            NEW.preco_executado,
            NEW.preco_executado,
            NEW.quantidade_executada
        )
        ON CONFLICT (ativo_base_id, minuto) DO UPDATE
        SET high = GREATEST(candles_ohlcv.high, EXCLUDED.high),
            low = LEAST(candles_ohlcv.low, EXCLUDED.low),
            close = EXCLUDED.close,
            volume = candles_ohlcv.volume + EXCLUDED.volume;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """,
    """
    CREATE OR REPLACE FUNCTION bloquear_alteracao_trades()
    RETURNS TRIGGER AS $$
    BEGIN
        RAISE EXCEPTION 'Trades sao imutaveis: nao podem ser alterados, apagados ou truncados';
    END;
    $$ LANGUAGE plpgsql;
    """,
    """
    CREATE OR REPLACE FUNCTION executar_matching_ordem()
    RETURNS TRIGGER AS $$
    DECLARE
        v_entrada ordens%ROWTYPE;
        v_contraparte ordens%ROWTYPE;
        v_restante_entrada NUMERIC(24, 8);
        v_restante_contraparte NUMERIC(24, 8);
        v_quantidade_exec NUMERIC(24, 8);
        v_preco_trade NUMERIC(24, 8);
        v_valor_trade NUMERIC(30, 8);
        v_comprador_id BIGINT;
        v_vendedor_id BIGINT;
        v_status_entrada VARCHAR(15);
        v_status_contraparte VARCHAR(15);
    BEGIN
        SELECT *
        INTO v_entrada
        FROM ordens
        WHERE id = NEW.id
        FOR UPDATE;

        IF NOT FOUND THEN
            RETURN NULL;
        END IF;

        IF v_entrada.status NOT IN ('aberta', 'parcial')
           OR v_entrada.quantidade_total <= v_entrada.quantidade_preenchida THEN
            RETURN NULL;
        END IF;

        v_restante_entrada :=
            v_entrada.quantidade_total - v_entrada.quantidade_preenchida;

        LOOP
            EXIT WHEN v_restante_entrada <= 0;

            IF v_entrada.tipo = 'BID' THEN
                SELECT *
                INTO v_contraparte
                FROM ordens
                WHERE ativo_base_id = v_entrada.ativo_base_id
                  AND tipo = 'ASK'
                  AND status IN ('aberta', 'parcial')
                  AND quantidade_total > quantidade_preenchida
                  AND preco <= v_entrada.preco
                  AND id <> v_entrada.id
                ORDER BY preco ASC, criado_em ASC, id ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED;
            ELSE
                SELECT *
                INTO v_contraparte
                FROM ordens
                WHERE ativo_base_id = v_entrada.ativo_base_id
                  AND tipo = 'BID'
                  AND status IN ('aberta', 'parcial')
                  AND quantidade_total > quantidade_preenchida
                  AND preco >= v_entrada.preco
                  AND id <> v_entrada.id
                ORDER BY preco DESC, criado_em ASC, id ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED;
            END IF;

            EXIT WHEN NOT FOUND;

            v_restante_contraparte :=
                v_contraparte.quantidade_total - v_contraparte.quantidade_preenchida;
            v_quantidade_exec := LEAST(v_restante_entrada, v_restante_contraparte);
            EXIT WHEN v_quantidade_exec <= 0;

            v_preco_trade := v_contraparte.preco;
            v_valor_trade := v_preco_trade * v_quantidade_exec;

            IF v_entrada.tipo = 'BID' THEN
                v_comprador_id := v_entrada.usuario_id;
                v_vendedor_id := v_contraparte.usuario_id;

                UPDATE carteiras
                SET saldo_bloqueado = saldo_bloqueado - (v_entrada.preco * v_quantidade_exec),
                    saldo_disponivel = saldo_disponivel
                        + GREATEST(v_entrada.preco - v_preco_trade, 0) * v_quantidade_exec
                WHERE usuario_id = v_comprador_id
                  AND ativo_id = 'BRL';

                INSERT INTO carteiras (usuario_id, ativo_id, saldo_disponivel, saldo_bloqueado)
                VALUES (v_comprador_id, v_entrada.ativo_base_id, v_quantidade_exec, 0)
                ON CONFLICT (usuario_id, ativo_id) DO UPDATE
                SET saldo_disponivel = carteiras.saldo_disponivel + EXCLUDED.saldo_disponivel;

                UPDATE carteiras
                SET saldo_bloqueado = saldo_bloqueado - v_quantidade_exec
                WHERE usuario_id = v_vendedor_id
                  AND ativo_id = v_entrada.ativo_base_id;

                INSERT INTO carteiras (usuario_id, ativo_id, saldo_disponivel, saldo_bloqueado)
                VALUES (v_vendedor_id, 'BRL', v_valor_trade, 0)
                ON CONFLICT (usuario_id, ativo_id) DO UPDATE
                SET saldo_disponivel = carteiras.saldo_disponivel + EXCLUDED.saldo_disponivel;
            ELSE
                v_comprador_id := v_contraparte.usuario_id;
                v_vendedor_id := v_entrada.usuario_id;

                UPDATE carteiras
                SET saldo_bloqueado = saldo_bloqueado - (v_contraparte.preco * v_quantidade_exec)
                WHERE usuario_id = v_comprador_id
                  AND ativo_id = 'BRL';

                INSERT INTO carteiras (usuario_id, ativo_id, saldo_disponivel, saldo_bloqueado)
                VALUES (v_comprador_id, v_entrada.ativo_base_id, v_quantidade_exec, 0)
                ON CONFLICT (usuario_id, ativo_id) DO UPDATE
                SET saldo_disponivel = carteiras.saldo_disponivel + EXCLUDED.saldo_disponivel;

                UPDATE carteiras
                SET saldo_bloqueado = saldo_bloqueado - v_quantidade_exec
                WHERE usuario_id = v_vendedor_id
                  AND ativo_id = v_entrada.ativo_base_id;

                INSERT INTO carteiras (usuario_id, ativo_id, saldo_disponivel, saldo_bloqueado)
                VALUES (v_vendedor_id, 'BRL', v_valor_trade, 0)
                ON CONFLICT (usuario_id, ativo_id) DO UPDATE
                SET saldo_disponivel = carteiras.saldo_disponivel + EXCLUDED.saldo_disponivel;
            END IF;

            v_status_contraparte := CASE
                WHEN v_contraparte.quantidade_preenchida + v_quantidade_exec
                     >= v_contraparte.quantidade_total THEN 'executada'
                ELSE 'parcial'
            END;

            UPDATE ordens
            SET quantidade_preenchida = quantidade_preenchida + v_quantidade_exec,
                status = v_status_contraparte
            WHERE id = v_contraparte.id;

            v_restante_entrada := v_restante_entrada - v_quantidade_exec;
            v_status_entrada := CASE
                WHEN v_restante_entrada <= 0 THEN 'executada'
                ELSE 'parcial'
            END;

            UPDATE ordens
            SET quantidade_preenchida = quantidade_total - v_restante_entrada,
                status = v_status_entrada
            WHERE id = v_entrada.id;

            INSERT INTO trades (
                ordem_maker_id,
                ordem_taker_id,
                comprador_id,
                vendedor_id,
                ativo_base_id,
                preco_executado,
                quantidade_executada,
                valor_executado
            )
            VALUES (
                v_contraparte.id,
                v_entrada.id,
                v_comprador_id,
                v_vendedor_id,
                v_entrada.ativo_base_id,
                v_preco_trade,
                v_quantidade_exec,
                v_valor_trade
            );
        END LOOP;

        RETURN NULL;
    END;
    $$ LANGUAGE plpgsql;
    """,
    """
    CREATE OR REPLACE FUNCTION get_best_orders(
        p_ativo_id VARCHAR(10),
        p_n INTEGER DEFAULT 5
    )
    RETURNS TABLE (
        tipo VARCHAR(4),
        posicao INTEGER,
        preco NUMERIC(24, 8),
        quantidade_disponivel NUMERIC(30, 8),
        quantidade_ordens BIGINT
    )
    AS $$
        WITH agrupadas AS (
            SELECT
                o.tipo,
                o.preco,
                SUM(o.quantidade_total - o.quantidade_preenchida) AS quantidade_disponivel,
                COUNT(*) AS quantidade_ordens
            FROM ordens o
            WHERE o.ativo_base_id = p_ativo_id
              AND o.status IN ('aberta', 'parcial')
              AND o.quantidade_total > o.quantidade_preenchida
            GROUP BY o.tipo, o.preco
        ),
        ranqueadas AS (
            SELECT
                a.*,
                ROW_NUMBER() OVER (
                    PARTITION BY a.tipo
                    ORDER BY
                        CASE WHEN a.tipo = 'BID' THEN a.preco END DESC NULLS LAST,
                        CASE WHEN a.tipo = 'ASK' THEN a.preco END ASC NULLS LAST
                ) AS posicao
            FROM agrupadas a
        )
        SELECT
            r.tipo,
            r.posicao::INTEGER,
            r.preco,
            r.quantidade_disponivel,
            r.quantidade_ordens
        FROM ranqueadas r
        WHERE r.posicao <= p_n
        ORDER BY
            CASE WHEN r.tipo = 'BID' THEN 1 ELSE 2 END,
            r.posicao;
    $$ LANGUAGE SQL STABLE;
    """,
    """
    CREATE OR REPLACE FUNCTION cancel_order(
        p_ordem_id BIGINT,
        p_usuario_id BIGINT DEFAULT NULL
    )
    RETURNS BOOLEAN AS $$
    DECLARE
        v_ordem ordens%ROWTYPE;
        v_restante NUMERIC(24, 8);
        v_ativo_devolver VARCHAR(10);
        v_valor_devolver NUMERIC(30, 8);
    BEGIN
        SELECT *
        INTO v_ordem
        FROM ordens
        WHERE id = p_ordem_id
        FOR UPDATE;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Ordem % nao encontrada', p_ordem_id;
        END IF;

        IF p_usuario_id IS NOT NULL AND v_ordem.usuario_id <> p_usuario_id THEN
            RAISE EXCEPTION 'Ordem % nao pertence ao usuario %', p_ordem_id, p_usuario_id;
        END IF;

        IF v_ordem.status NOT IN ('aberta', 'parcial') THEN
            RETURN FALSE;
        END IF;

        v_restante := v_ordem.quantidade_total - v_ordem.quantidade_preenchida;

        IF v_ordem.tipo = 'BID' THEN
            v_ativo_devolver := 'BRL';
            v_valor_devolver := v_ordem.preco * v_restante;
        ELSE
            v_ativo_devolver := v_ordem.ativo_base_id;
            v_valor_devolver := v_restante;
        END IF;

        UPDATE carteiras
        SET saldo_bloqueado = saldo_bloqueado - v_valor_devolver,
            saldo_disponivel = saldo_disponivel + v_valor_devolver
        WHERE usuario_id = v_ordem.usuario_id
          AND ativo_id = v_ativo_devolver;

        IF NOT FOUND THEN
            RAISE EXCEPTION
                'Carteira nao encontrada para devolucao da ordem %',
                p_ordem_id;
        END IF;

        UPDATE ordens
        SET status = 'cancelada'
        WHERE id = p_ordem_id;

        RETURN TRUE;
    END;
    $$ LANGUAGE plpgsql;
    """,
    """
    CREATE OR REPLACE FUNCTION user_portfolio(p_usuario_id BIGINT)
    RETURNS TABLE (
        ativo_id VARCHAR(10),
        saldo_disponivel NUMERIC(30, 8),
        saldo_bloqueado NUMERIC(30, 8),
        saldo_total NUMERIC(30, 8),
        ultimo_preco_brl NUMERIC(24, 8),
        valor_total_brl NUMERIC(38, 8)
    )
    AS $$
        SELECT
            c.ativo_id,
            c.saldo_disponivel,
            c.saldo_bloqueado,
            c.saldo_disponivel + c.saldo_bloqueado AS saldo_total,
            CASE
                WHEN c.ativo_id = 'BRL' THEN 1.00000000
                ELSE COALESCE(ultimo.preco_executado, 0.00000000)
            END AS ultimo_preco_brl,
            (c.saldo_disponivel + c.saldo_bloqueado) *
            CASE
                WHEN c.ativo_id = 'BRL' THEN 1.00000000
                ELSE COALESCE(ultimo.preco_executado, 0.00000000)
            END AS valor_total_brl
        FROM carteiras c
        LEFT JOIN LATERAL (
            SELECT t.preco_executado
            FROM trades t
            WHERE t.ativo_base_id = c.ativo_id
            ORDER BY t.executado_em DESC, t.id DESC
            LIMIT 1
        ) ultimo ON c.ativo_id <> 'BRL'
        WHERE c.usuario_id = p_usuario_id
        ORDER BY valor_total_brl DESC, c.ativo_id;
    $$ LANGUAGE SQL STABLE;
    """,
    """
    CREATE OR REPLACE VIEW view_market_summary AS
    SELECT
        a.id AS ativo_id,
        a.nome AS ativo_nome,
        ultimo.preco_executado AS ultimo_preco,
        CASE
            WHEN preco_24h.preco_executado IS NULL OR preco_24h.preco_executado = 0 THEN NULL
            ELSE ROUND(
                ((ultimo.preco_executado - preco_24h.preco_executado)
                 / preco_24h.preco_executado) * 100,
                8
            )
        END AS variacao_24h_percentual,
        COALESCE(volume_24h.volume_24h, 0.00000000) AS volume_24h,
        melhor_bid.preco AS melhor_bid,
        melhor_ask.preco AS melhor_ask,
        melhor_ask.preco - melhor_bid.preco AS spread_atual
    FROM ativos a
    LEFT JOIN LATERAL (
        SELECT t.preco_executado
        FROM trades t
        WHERE t.ativo_base_id = a.id
        ORDER BY t.executado_em DESC, t.id DESC
        LIMIT 1
    ) ultimo ON TRUE
    LEFT JOIN LATERAL (
        SELECT t.preco_executado
        FROM trades t
        WHERE t.ativo_base_id = a.id
          AND t.executado_em <= clock_timestamp() - INTERVAL '24 hours'
        ORDER BY t.executado_em DESC, t.id DESC
        LIMIT 1
    ) preco_24h ON TRUE
    LEFT JOIN LATERAL (
        SELECT SUM(t.quantidade_executada) AS volume_24h
        FROM trades t
        WHERE t.ativo_base_id = a.id
          AND t.executado_em >= clock_timestamp() - INTERVAL '24 hours'
    ) volume_24h ON TRUE
    LEFT JOIN LATERAL (
        SELECT o.preco
        FROM ordens o
        WHERE o.ativo_base_id = a.id
          AND o.tipo = 'BID'
          AND o.status IN ('aberta', 'parcial')
          AND o.quantidade_total > o.quantidade_preenchida
        ORDER BY o.preco DESC, o.criado_em ASC, o.id ASC
        LIMIT 1
    ) melhor_bid ON TRUE
    LEFT JOIN LATERAL (
        SELECT o.preco
        FROM ordens o
        WHERE o.ativo_base_id = a.id
          AND o.tipo = 'ASK'
          AND o.status IN ('aberta', 'parcial')
          AND o.quantidade_total > o.quantidade_preenchida
        ORDER BY o.preco ASC, o.criado_em ASC, o.id ASC
        LIMIT 1
    ) melhor_ask ON TRUE
    WHERE a.id <> 'BRL';
    """,
    """
    CREATE OR REPLACE VIEW view_trades_history AS
    SELECT
        t.id AS trade_id,
        t.ativo_base_id,
        a.nome AS ativo_nome,
        t.preco_executado,
        t.quantidade_executada,
        t.valor_executado,
        t.ordem_maker_id,
        t.ordem_taker_id,
        comprador.nome AS comprador,
        vendedor.nome AS vendedor,
        t.executado_em
    FROM trades t
    JOIN ativos a ON a.id = t.ativo_base_id
    LEFT JOIN usuarios comprador ON comprador.id = t.comprador_id
    LEFT JOIN usuarios vendedor ON vendedor.id = t.vendedor_id
    ORDER BY t.executado_em DESC, t.id DESC;
    """,
    """
    CREATE OR REPLACE VIEW view_traders_ranking AS
    WITH participantes AS (
        SELECT
            t.comprador_id AS usuario_id,
            t.valor_executado,
            t.quantidade_executada
        FROM trades t
        WHERE t.executado_em >= clock_timestamp() - INTERVAL '24 hours'

        UNION ALL

        SELECT
            t.vendedor_id AS usuario_id,
            t.valor_executado,
            t.quantidade_executada
        FROM trades t
        WHERE t.executado_em >= clock_timestamp() - INTERVAL '24 hours'
    ),
    agregado AS (
        SELECT
            p.usuario_id,
            COUNT(*) AS total_negocios,
            SUM(p.quantidade_executada) AS quantidade_total,
            SUM(p.valor_executado) AS volume_brl_24h
        FROM participantes p
        WHERE p.usuario_id IS NOT NULL
        GROUP BY p.usuario_id
    )
    SELECT
        DENSE_RANK() OVER (ORDER BY a.volume_brl_24h DESC) AS posicao,
        u.id AS usuario_id,
        u.nome,
        a.total_negocios,
        a.quantidade_total,
        a.volume_brl_24h
    FROM agregado a
    JOIN usuarios u ON u.id = a.usuario_id
    ORDER BY posicao, u.id;
    """,
    """
    DROP TRIGGER IF EXISTS trg_preparar_ordem_insert ON ordens;
    """,
    """
    CREATE TRIGGER trg_preparar_ordem_insert
    BEFORE INSERT ON ordens
    FOR EACH ROW
    EXECUTE FUNCTION preparar_ordem_insert();
    """,
    """
    DROP TRIGGER IF EXISTS trg_executar_matching_ordem ON ordens;
    """,
    """
    CREATE TRIGGER trg_executar_matching_ordem
    AFTER INSERT ON ordens
    FOR EACH ROW
    EXECUTE FUNCTION executar_matching_ordem();
    """,
    """
    DROP TRIGGER IF EXISTS trg_auditar_status_ordens ON ordens;
    """,
    """
    CREATE TRIGGER trg_auditar_status_ordens
    AFTER INSERT OR UPDATE OF status ON ordens
    FOR EACH ROW
    EXECUTE FUNCTION auditar_status_ordem();
    """,
    """
    DROP TRIGGER IF EXISTS trg_atualizar_candle_trade ON trades;
    """,
    """
    CREATE TRIGGER trg_atualizar_candle_trade
    AFTER INSERT ON trades
    FOR EACH ROW
    EXECUTE FUNCTION atualizar_candle_trade();
    """,
    """
    DROP TRIGGER IF EXISTS trg_bloquear_alteracao_trades ON trades;
    """,
    """
    CREATE TRIGGER trg_bloquear_alteracao_trades
    BEFORE UPDATE OR DELETE OR TRUNCATE ON trades
    FOR EACH STATEMENT
    EXECUTE FUNCTION bloquear_alteracao_trades();
    """,
]


def criar_tabelas():
    connection = None
    cursor = None

    try:
        print("Conectando ao PostgreSQL...")
        connection = psycopg2.connect(**bd_configuracoes)
        cursor = connection.cursor()

        for query in queryParaSubirBanco:
            cursor.execute(query)

        connection.commit()
        print("Banco montado com tabelas, indices, triggers, funcoes e views.")
        print("Motor de matching, auditoria, candles e trades imutaveis estao prontos.")

    except Error as e:
        print(f"Erro ao executar script no PostgreSQL: {e}")
        if connection:
            connection.rollback()

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
            print("Conexao com o PostgreSQL encerrada.")

if __name__ == "__main__":
    criar_tabelas()
