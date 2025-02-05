import os
import asyncpg
import logging
from fastapi import FastAPI
import json

logger = logging.getLogger("uvicorn")

DATABASE_URL = os.getenv("DB_URL", "postgresql://user:pass@db:5432/rinha")

pool = None


async def connect(url=DATABASE_URL):
    global pool
    try:
        logger.info(f"Connecting to db {url}")
        pool = await asyncpg.create_pool(
            url, max_size=int(os.getenv("DB_POOL", 10)), timeout=30
        )
        await create_tables()
    except Exception as err:
        logger.error(f"An error occurred when connecting: {err}")


async def close():
    await pool.close()


async def create_tables():
    logger.info(f"Creating table 'pessoas' if not exists")
    async with pool.acquire() as conn:
        await conn.execute(
            """
        CREATE EXTENSION IF NOT EXISTS "pgcrypto";
        CREATE EXTENSION IF NOT EXISTS "pg_trgm";

        CREATE OR REPLACE FUNCTION generate_searchable(_nome VARCHAR, _apelido VARCHAR, _stack JSON)
        RETURNS TEXT AS $$
        BEGIN
        RETURN _nome || _apelido || _stack;
        END;
        $$ LANGUAGE plpgsql IMMUTABLE;

        CREATE TABLE IF NOT EXISTS pessoas (
            id UUID UNIQUE NOT NULL,
            apelido TEXT UNIQUE NOT NULL,
            nome TEXT NOT NULL,
            nascimento DATE NOT NULL,
            stack JSON,
            searchable TEXT GENERATED ALWAYS AS (generate_searchable(nome, apelido, stack)) STORED
        );

        CREATE INDEX IF NOT EXISTS idx_pessoas_searchable ON pessoas USING gist(searchable gist_trgm_ops);
        """
        )


async def insert_person(id, apelido, nome, nascimento, stack):
    async with pool.acquire() as conn:
        stack_json = json.dumps(stack)
        await conn.execute(
            """
        INSERT INTO pessoas(id, apelido, nome, nascimento, stack)
        VALUES ($1, $2, $3, $4, $5);
        """,
            id,
            apelido,
            nome,
            nascimento,
            stack_json,
        )


async def find_by_id(id):
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
        SELECT id, apelido, nome, nascimento, stack
        FROM pessoas
        WHERE id = $1;
        """,
            id,
        )
        return result


async def find_by_term(term):
    async with pool.acquire() as conn:
        result = await conn.fetch(
            """
        SELECT id, apelido, nome, nascimento, stack
        FROM pessoas
        WHERE searchable ILIKE $1
        LIMIT 50;
        """,
            f"%{term}%",
        )
        return result


async def exists_by_apelido(apelido):
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
        SELECT COUNT(1)
        FROM pessoas
        WHERE apelido = $1;
        """,
            apelido,
        )
        return True if result["count"] else False


async def count_people():
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
        SELECT COUNT(1)
        FROM pessoas;
        """
        )
        return result[0]
