"""
Sentinel AI — Knowledge Base Engine (PostgreSQL edition)
"""

import re, json, datetime
from typing import List, Dict, Optional

import torch
import torch.nn.functional as F


class KnowledgeBase:

    def __init__(self, device: str = 'cpu'):
        self.device = device

        from sentence_transformers import SentenceTransformer
        self.encoder = SentenceTransformer(
            'paraphrase-multilingual-MiniLM-L12-v2', device=device)

        self.docs:       List[Dict] = []
        self.chunks:     List[str]  = []
        self.chunk_dids: List[int]  = []
        self.vectors:    Optional[torch.Tensor] = None

    async def load_from_db(self):
        from database import db_list_documents, db_get_all_chunks
        try:
            docs   = await db_list_documents()
            chunks = await db_get_all_chunks()
        except Exception as e:
            print(f"❌ PostgreSQL недоступен: {e}")
            return

        if not docs:
            print("📭 БД пуста — загружаем демо-документы...")
            await self._load_demo_docs()
            return

        self.docs = []
        for d in docs:
            self.docs.append({
                'id':         d['id'],
                'name':       d['name'],
                'category':   d['category'],
                'size':       d['size'],
                'chunks':     d['chunk_count'],
                'created_at': str(d['created_at']),
            })

        self.chunks     = []
        self.chunk_dids = []
        stored_vecs     = []
        has_bad_vec     = False

        for ch in chunks:
            self.chunks.append(ch['content'])
            self.chunk_dids.append(ch['doc_id'])
            if ch.get('vector'):
                try:
                    v = json.loads(ch['vector'])
                    if len(v) == 384:
                        stored_vecs.append(v)
                    else:
                        stored_vecs.append(None)
                        has_bad_vec = True
                except Exception:
                    stored_vecs.append(None)
                    has_bad_vec = True
            else:
                stored_vecs.append(None)
                has_bad_vec = True

        if self.chunks:
            if not has_bad_vec and len(stored_vecs) == len(self.chunks):
                try:
                    self.vectors = F.normalize(
                        torch.tensor(stored_vecs, dtype=torch.float32), p=2, dim=-1)
                    print(f"⚡ Векторы восстановлены из БД ({len(self.chunks)} шт.)")
                except Exception:
                    self.vectors = self._encode(self.chunks)
                    print(f"⚡ Векторы пересчитаны ({len(self.chunks)} шт.)")
            else:
                self.vectors = self._encode(self.chunks)
                print(f"⚡ Векторы пересчитаны ({len(self.chunks)} шт.)")

        print(f"✅ KB loaded from DB: {len(self.docs)} docs, {len(self.chunks)} chunks")

    async def add_document_async(self, name: str, content: str, category: str = 'Общее') -> Dict:
        from database import db_create_document, db_update_chunk_count, db_save_chunks

        content = content.replace('\x00', '')
        row     = await db_create_document(name, content, category)
        doc_id  = row['id']

        new_chunks = self._make_chunks(content)
        new_start  = len(self.chunks)

        self.chunks.extend(new_chunks)
        self.chunk_dids.extend([doc_id] * len(new_chunks))

        self.vectors = self._encode(self.chunks)

        vecs_list = self.vectors[new_start:new_start + len(new_chunks)].tolist()
        await db_save_chunks(doc_id, new_chunks, vecs_list)
        await db_update_chunk_count(doc_id, len(new_chunks))

        doc = {
            'id':         doc_id,
            'name':       name,
            'category':   category,
            'size':       len(content),
            'chunks':     len(new_chunks),
            'created_at': datetime.datetime.now().strftime('%d.%m.%Y %H:%M'),
        }
        self.docs.append(doc)
        return doc

    def add_document(self, name: str, content: str, category: str = 'Общее') -> Dict:
        doc_id = max((d['id'] for d in self.docs), default=-1) + 1
        chunks = self._make_chunks(content)

        self.chunks.extend(chunks)
        self.chunk_dids.extend([doc_id] * len(chunks))
        self.vectors = self._encode(self.chunks)

        doc = {
            'id':         doc_id,
            'name':       name,
            'category':   category,
            'content':    content,
            'size':       len(content),
            'chunks':     len(chunks),
            'created_at': datetime.datetime.now().strftime('%d.%m.%Y %H:%M'),
        }
        self.docs.append(doc)
        return doc

    async def delete_document_async(self, doc_id: int):
        from database import db_delete_document
        await db_delete_document(doc_id)
        self._remove_from_index(doc_id)

    def delete_document(self, doc_id: int) -> bool:
        self._remove_from_index(doc_id)
        return True

    def list_documents(self) -> List[Dict]:
        return self.docs

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        if self.vectors is None or not self.chunks:
            return []
        q_vec  = self._encode([query])
        scores = torch.matmul(q_vec, self.vectors.T).squeeze(0)
        k      = min(top_k, len(self.chunks))
        top    = scores.topk(k).indices.tolist()
        results = []
        for idx in top:
            did = self.chunk_dids[idx]
            doc = next((d for d in self.docs if d['id'] == did), None)
            results.append({
                'chunk':    self.chunks[idx],
                'doc_name': doc['name']     if doc else '?',
                'category': doc['category'] if doc else '',
                'score':    round(float(scores[idx]), 4),
            })
        return results

    def answer(self, question: str) -> Dict:
        results = self.search(question, top_k=8)
        if not results:
            return {'answer': 'База знаний пуста. Загрузите документы.',
                    'sources': [], 'confidence': 0.0, 'found': False}

        best_score = results[0]['score']
        if best_score < 0.3:
            return {'answer': f'По запросу «{question}» ничего не найдено.',
                    'sources': [], 'confidence': round(best_score * 100, 1), 'found': False}

        q_words      = set(re.findall(r'\b\w+\b', question.lower()))
        scored_sents = []
        used_sources = []

        for r in results[:5]:
            for sent in re.split(r'[.!?\n]+', r['chunk']):
                sent = sent.strip()
                if len(sent) < 15:
                    continue
                sw      = set(re.findall(r'\b\w+\b', sent.lower()))
                overlap = len(q_words & sw) / max(len(q_words), 1)
                scored_sents.append((overlap + r['score'], sent, r['doc_name']))
            if r['doc_name'] not in used_sources:
                used_sources.append(r['doc_name'])

        scored_sents.sort(key=lambda x: -x[0])
        seen, lines = set(), []
        for _, sent, _ in scored_sents[:6]:
            if sent not in seen:
                seen.add(sent)
                lines.append(sent)

        if not lines:
            lines = [s.strip() for s in results[0]['chunk'].split('.')
                     if len(s.strip()) > 15][:4]

        answer = ' '.join(lines)
        if used_sources:
            answer += f'\n\n📄 Источник: {", ".join(used_sources[:3])}'

        return {'answer': answer, 'sources': used_sources,
                'confidence': round(best_score * 100, 1), 'found': True}

    def stats(self) -> Dict:
        return {
            'total_docs':     len(self.docs),
            'total_chunks':   len(self.chunks),
            'vocab_size':     10000,
            'encoder_params': 0,
            'has_index':      self.vectors is not None,
            'embedding_dim':  384,
        }

    def _make_chunks(self, text: str, chunk_size=80, overlap=20) -> List[str]:
        words  = text.split()
        step   = max(1, chunk_size - overlap)
        chunks = []
        for i in range(0, max(1, len(words)), step):
            chunk = ' '.join(words[i:i + chunk_size])
            if len(chunk.strip()) > 15:
                chunks.append(chunk)
        return chunks or [text[:500]]

    def _remove_from_index(self, doc_id: int):
        self.docs = [d for d in self.docs if d['id'] != doc_id]
        keep = [i for i, did in enumerate(self.chunk_dids) if did != doc_id]
        self.chunks     = [self.chunks[i]     for i in keep]
        self.chunk_dids = [self.chunk_dids[i] for i in keep]
        self.vectors    = self.vectors[keep] if self.vectors is not None and keep else None

    def _encode(self, texts: List[str]) -> torch.Tensor:
        if not texts:
            return torch.zeros(0, 384)
        vecs = self.encoder.encode(
            texts, convert_to_tensor=True,
            show_progress_bar=False, device=self.device)
        return F.normalize(vecs.cpu(), p=2, dim=-1)

    async def _load_demo_docs(self):
        demo = [
            ("Политика безопасности", "Безопасность",
             "Политика информационной безопасности компании версия 2.1. "
             "Все пароли должны содержать минимум 12 символов, включать буквы, цифры и спецсимволы. "
             "Пароли необходимо менять каждые 90 дней. Двухфакторная аутентификация обязательна для всех сотрудников. "
             "VPN обязателен при работе вне офиса. Инциденты безопасности сообщаются в IT в течение 1 часа. "
             "Конфиденциальные данные клиентов не передаются третьим лицам без письменного согласия руководства."),
            ("HR Процедуры", "HR",
             "Процедуры отдела кадров версия 3.0. Заявка на ежегодный отпуск подаётся минимум за 14 дней, форма ФО-07. "
             "Ежегодный оплачиваемый отпуск 28 дней. Больничный лист сдаётся в HR в течение 5 рабочих дней. "
             "Испытательный срок 3 месяца. Корпоративная медицинская страховка с первого дня. "
             "Дресс-код: smart casual в офисе, деловой стиль при встречах с клиентами."),
            ("Финансовый регламент", "Финансы",
             "Финансовые правила компании версия 1.5. Корпоративная карта оформляется через бухгалтерию по форме ФН-12. "
             "Лимит по карте для сотрудников 50000 тенге в месяц, для руководителей 150000 тенге. "
             "Авансовый отчёт сдаётся до 5-го числа следующего месяца. Командировочные суточные 5000 тенге. "
             "Представительские расходы свыше 30000 тенге согласовываются с директором."),
            ("IT Безопасность", "IT",
             "Регламент IT-безопасности версия 2.0. VPN обязателен при удалённой работе и публичных WiFi-сетях. "
             "Запрещено устанавливать ПО без согласования с IT-отделом. "
             "Рабочие файлы хранятся только на корпоративных серверах. Пароли менять каждые 90 дней. "
             "Фишинговые письма пересылать на security@company.kz."),
            ("Кодекс этики", "Этика",
             "Кодекс корпоративного поведения и этики. Уважительное отношение ко всем сотрудникам обязательно. "
             "Конфликт интересов необходимо сообщать руководству в письменном виде. "
             "Запрещено принимать подарки от клиентов стоимостью свыше 5000 тенге. "
             "Конфиденциальность информации сохраняется в течение 2 лет после увольнения."),
        ]
        print(f"📥 Загрузка {len(demo)} демо-документов в PostgreSQL...")
        for name, cat, content in demo:
            try:
                await self.add_document_async(name, content, cat)
                print(f"  ✓ {name}")
            except Exception as e:
                print(f"  ✗ {name}: {e}")
        print(f"✅ Demo docs loaded: {len(self.docs)} docs, {len(self.chunks)} chunks")