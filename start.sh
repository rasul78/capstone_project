#!/bin/bash
# ─────────────────────────────────────────────────────
# Sentinel AI — Setup & Run Script
# ─────────────────────────────────────────────────────
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  🛡  Sentinel AI Platform v3.0  ${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Check Docker
if ! command -v docker &> /dev/null; then
  echo -e "${YELLOW}⚠ Docker не найден. Установите Docker Desktop.${NC}"
  exit 1
fi

if ! command -v docker compose &> /dev/null; then
  echo -e "${YELLOW}⚠ docker compose не найден.${NC}"
  exit 1
fi

echo -e "\n${GREEN}1. Запуск PostgreSQL...${NC}"
docker compose up -d postgres
echo "   Ожидание готовности БД..."
sleep 5

echo -e "\n${GREEN}2. Запуск Backend (FastAPI)...${NC}"
docker compose up -d backend

echo -e "\n${GREEN}3. Запуск Frontend (React)...${NC}"
docker compose up -d frontend

echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅ Sentinel AI запущен!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  🌐 Frontend:  ${BLUE}http://localhost:3000${NC}"
echo -e "  🔌 Backend:   ${BLUE}http://localhost:8000${NC}"
echo -e "  📚 API Docs:  ${BLUE}http://localhost:8000/docs${NC}"
echo -e "  🐘 PostgreSQL: ${BLUE}localhost:5432 / sentinel_ai${NC}"
echo ""
echo -e "  Логи:  docker compose logs -f"
echo -e "  Стоп:  docker compose down"
echo ""
