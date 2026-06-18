# Simulador HFT - LBD

Alunos:

- Joao Pedro de Souza Quintino de Paula - RGA: 202019060598
- Anália Beatriz Ferreira da Cruz- RGA: 202119060751

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

O arquivo `dump_banco.sql` tambem pode ser entregue/importado diretamente para
criar as tabelas, funcoes, triggers e views. O `trabalho.py` apenas executa esse
dump no banco configurado. Ao rodar o dump, as tabelas do trabalho sao recriadas.

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

## Usando o dump diretamente

```bash
psql -h localhost -p 5433 -U postgres -d banco_trabalho -f dump_banco.sql
```

## Consultas uteis

```sql
SELECT * FROM get_best_orders('BTC', 5);
SELECT cancel_order(1);
SELECT * FROM user_portfolio(1);
SELECT * FROM view_market_summary;
SELECT * FROM view_trades_history LIMIT 20;
SELECT * FROM view_traders_ranking LIMIT 20;
```
