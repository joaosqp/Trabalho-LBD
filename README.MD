# Simulador HFT - LBD

Alunos:

- Joao Pedro de Souza Quintino de Paula - RGA: 202019060598
- Analia - RGA: 202119060751

## Como executar

1. Subir o PostgreSQL:

```bash
docker compose -f postgresql.yml up -d
```

2. Instalar a dependencia Python:

```bash
pip install -r requirements.txt
```

3. Criar a estrutura completa do banco:

```bash
python trabalho.py
```

4. Popular o banco ate o volume exigido:

```bash
python popular_dados.py
```

O gerador usa 4 processos, faz insercoes em lote, gera pequenas variacoes de
preco a partir do preco anterior e para quando o banco atinge o volume definido
no inicio do arquivo.

## Objetos criados

- Usuarios, ativos e carteiras com saldo disponivel e saldo bloqueado.
- Livro de ordens com BID/ASK e estados aberta, parcial, executada e cancelada.
- Trigger de matching com prioridade de preco e tempo, usando `FOR UPDATE SKIP LOCKED`.
- Registro imutavel de trades.
- Candles OHLCV por minuto com particionamento.
- Auditoria de mudancas de estado das ordens.
- Funcoes `get_best_orders`, `cancel_order` e `user_portfolio`.
- Views `view_market_summary`, `view_trades_history` e `view_traders_ranking`.

## Consultas uteis

```sql
SELECT * FROM get_best_orders('BTC', 5);
SELECT cancel_order(1);
SELECT * FROM user_portfolio(1);
SELECT * FROM view_market_summary;
SELECT * FROM view_trades_history LIMIT 20;
SELECT * FROM view_traders_ranking LIMIT 20;
```
