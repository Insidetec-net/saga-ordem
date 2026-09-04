# Order Saga E-Commerce 🚀

[![CI](https://github.com/Insidetec-net/saga-ordem/actions/workflows/ci.yml/badge.svg)](https://github.com/Insidetec-net/saga-ordem/actions/workflows/ci.yml)

Sistema de E-commerce construído com arquitetura robusta de microsserviços focando em confiabilidade, consistência eventual e resiliência de alto desempenho.

Este projeto demonstra a implementação de padrões de software modernos para sistemas distribuídos.

## 🏗 Arquitetura & Padrões

*   **Saga Pattern (Orchestration):** Garante a consistência de dados em operações distribuídas (ex: debitar estoque e cobrar pagamento). Se uma etapa falha, as transações anteriores são revertidas de forma compensatória.
*   **Outbox Pattern (Transactional Outbox):** A API salva os eventos no banco de dados na mesma transação atômica da regra de negócios. Um worker background coleta esses eventos para garantir 100% de confiabilidade na publicação (At-least-once delivery).
*   **Idempotency API:** Todas as chamadas POST mutáveis exigem um `X-Idempotency-Key`. Se a rede oscilar, o cliente pode tentar a requisição novamente sem o risco de duplicação, graças ao controle distribuído no Redis.
*   **Dead Letter Queue (DLQ):** Eventos que falham repetidas vezes são segregados para uma DLQ relacional e não bloqueiam o ecossistema.
*   **Optimistic Concurrency Control:** O controle de concorrência impede atualizações conflitantes na versão da Saga e dos agregados usando controle baseado na versão do banco.
*   **Domain-Driven Design (DDD):** Lógica encapsulada em *Aggregates*, *Entities* e *Value Objects*.
*   **Dependency Inversion & Clean Architecture:** Isolamento de regras de negócios da infraestrutura via abstrações, o que permitiu mudar de SQLite local para PostgreSQL+Redis+Celery sem reescrever 1 linha de regra de negócio!

## 🛠 Stack Tecnológica

*   **Linguagem:** Python 3.12+
*   **Web Framework:** FastAPI, Pydantic V2
*   **Banco de Dados (Relacional/Async):** PostgreSQL, SQLAlchemy 2.0 (AsyncIO), Alembic, asyncpg
*   **Task Queue & Workers:** Celery (com fork-pool para concorrência)
*   **Cache & Idempotency Store:** Redis, redis.asyncio
*   **Testes:** Pytest, pytest-asyncio, httpx, unittest.mock
*   **Infra/Orquestração:** Docker & Docker Compose

## 🚀 Como Rodar o Projeto

Você precisa do **Docker** e do **Docker Compose** instalados na sua máquina.

1. **Clone o repositório:**
```bash
git clone https://github.com/Insidetec-net/saga-ordem.git
cd saga-ordem
```

2. **Inicie a Infraestrutura e a Aplicação:**
```bash
docker-compose up -d --build
```
Isso vai criar os contêineres:
*   `saga-postgres`: O banco de dados relacional.
*   `saga-redis`: Banco chave-valor em memória.
*   `saga-api`: O servidor FastAPI rodando na porta `8000`.
*   `saga-worker`: O Worker Celery processando os eventos em background.

3. **Gere as Tabelas do Banco de Dados:**
```bash
docker exec -it saga-api ./scripts/run_migrations.sh
```

4. **Carregue os Dados Iniciais (Seed):**
```bash
docker exec -it saga-api ./scripts/seed_data.sh
```

5. **Acesse a API e a Documentação:**
- Abra o navegador em: [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI interativo)

## 🧪 Rodando a Bateria de Testes

A suíte de testes E2E e unitários conta com validações extremas (Testes de Compensação da Saga, Concorrência de 10 requisições simultâneas e DLQ).

Para rodar os testes, use o ambiente virtual:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -e .[dev]
pytest tests/ -v
```

## 📂 Estrutura de Diretórios

```
.
├── src/
│   ├── api/             # Camada Web: Rotas FastAPI, Schemas, Main app
│   ├── application/     # Casos de Uso: Orchestrator, Saga Steps, Reconciliação
│   ├── domain/          # Coração do Sistema: Models, Events, Exceptions
│   ├── infrastructure/  # Camada de Adaptação externa: Banco, Redis, Repositórios
│   └── workers/         # Ponto de entrada do Celery
├── tests/               # Testes Unitários, Integração e E2E
├── scripts/             # Ferramentas úteis de banco
├── alembic/             # Versões de Migrações do banco de dados
├── docker/              # Dockerfiles customizados
└── docker-compose.yml   # Definição do ecossistema local
```

## ✨ Licença

Este projeto é de código aberto e está sob a licença MIT. Desenvolvido para fins de estudo, portfolio e comprovação de proficiência em arquiteturas distribuídas.
