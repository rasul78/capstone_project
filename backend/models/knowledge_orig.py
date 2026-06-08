"""
Sentinel AI — Knowledge Base Engine
Собственная нейросеть для семантического поиска по документам.

Архитектура:
  SimpleTokenizer   → токенизация текста (BPE-like по частоте)
  MiniTransformer   → трансформер-энкодер (2 слоя, d=128, 4 головы)
  KnowledgeBase     → векторная база + RAG (поиск + генерация ответа)

Пайплайн запроса:
  вопрос → токенизация → MiniTransformer → вектор запроса 128d
  чанки  → токенизация → MiniTransformer → матрица векторов N×128
  cosine similarity → top-K чанков → извлечение ответа
"""

import re
import math
import datetime
from collections import Counter
from typing import List, Dict, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F


# ─────────────────────────────────────────────────────
#  Токенизатор
# ─────────────────────────────────────────────────────
class SimpleTokenizer:
    SPECIAL = {'[PAD]': 0, '[UNK]': 1, '[CLS]': 2, '[SEP]': 3}

    def __init__(self, vocab_size: int = 10000, max_len: int = 128):
        self.vocab_size = vocab_size
        self.max_len    = max_len
        self.vocab      = dict(self.SPECIAL)
        self.fitted     = False

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r'\b\w+\b', text.lower())

    def fit(self, texts: List[str]):
        counts = Counter(t for tx in texts for t in self._tokenize(tx))
        for word, _ in counts.most_common(self.vocab_size - len(self.SPECIAL)):
            if word not in self.vocab:
                self.vocab[word] = len(self.vocab)
        self.fitted = True

    def encode(self, text: str) -> Tuple[List[int], List[int]]:
        tokens = ['[CLS]'] + self._tokenize(text)[:self.max_len - 2] + ['[SEP]']
        ids    = [self.vocab.get(t, 1) for t in tokens]
        mask   = [1] * len(ids)
        pad    = self.max_len - len(ids)
        return ids + [0] * pad, mask + [0] * pad

    def encode_batch(self, texts: List[str]) -> Tuple[torch.Tensor, torch.Tensor]:
        ids_list, mask_list = zip(*(self.encode(t) for t in texts))
        return (
            torch.tensor(ids_list, dtype=torch.long),
            torch.tensor(mask_list, dtype=torch.long),
        )


# ─────────────────────────────────────────────────────
#  Мини-трансформер энкодер
# ─────────────────────────────────────────────────────
class MiniTransformer(nn.Module):
    """
    Лёгкий трансформер для семантической векторизации текста.
    Вход:  sequence of token ids [B, L]
    Выход: L2-нормализованный вектор [B, d]
    """
    def __init__(self, vocab_size: int = 10000, d: int = 128,
                 heads: int = 4, layers: int = 2, max_len: int = 128):
        super().__init__()
        self.emb  = nn.Embedding(vocab_size, d, padding_idx=0)
        # Позиционное кодирование (sin/cos)
        pe = torch.zeros(max_len, d)
        pos = torch.arange(max_len).float().unsqueeze(1)
        div = torch.exp(
            torch.arange(0, d, 2).float() * (-math.log(10000.0) / d)
        )
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)
        self.register_buffer('pe', pe.unsqueeze(0))

        enc_layer = nn.TransformerEncoderLayer(
            d_model=d, nhead=heads, dim_feedforward=d * 4,
            dropout=0.1, batch_first=True, norm_first=True,
        )
        self.transformer = nn.TransformerEncoder(enc_layer, num_layers=layers)
        self.proj        = nn.Linear(d, d)

    def forward(self, ids: torch.Tensor,
                mask: torch.Tensor) -> torch.Tensor:
        x = self.emb(ids) + self.pe[:, :ids.size(1)]
        # padding_mask: True = игнорировать токен
        x = self.transformer(x, src_key_padding_mask=(mask == 0))
        # Mean pooling по непадингованным токенам
        m   = mask.unsqueeze(-1).float()
        vec = (x * m).sum(1) / m.sum(1).clamp(min=1e-9)
        return F.normalize(self.proj(vec), p=2, dim=-1)


# ─────────────────────────────────────────────────────
#  Knowledge Base — RAG система
# ─────────────────────────────────────────────────────
class KnowledgeBase:
    """
    Полная RAG система:
      1. add_document() → чанкинг с overlap → fit tokenizer → encode → store vectors
      2. search(query)  → encode query → cosine similarity → top-K чанков
      3. answer(query)  → search → extract best sentences → format answer
    """

    def __init__(self, device: str = 'cpu'):
        self.device  = device
        self.tok     = SimpleTokenizer(vocab_size=10000, max_len=128)
        self.encoder = MiniTransformer(
            vocab_size=10000, d=128, heads=4, layers=2
        ).to(device)
        self.encoder.eval()

        # Хранилище
        self.docs:       List[Dict] = []
        self.chunks:     List[str]  = []
        self.chunk_dids: List[int]  = []
        self.vectors:    Optional[torch.Tensor] = None
        self._id_counter = 0

        # Загружаем демо-документы
        self._load_demo_docs()

    # ── Public API ───────────────────────────────────

    def add_document(self, name: str, content: str,
                     category: str = 'Общее') -> Dict:
        doc_id = self._id_counter
        self._id_counter += 1
        doc = {
            'id':         doc_id,
            'name':       name,
            'category':   category,
            'content':    content,
            'size':       len(content),
            'chunks':     0,
            'created_at': datetime.datetime.now().strftime('%d.%m.%Y %H:%M'),
        }
        self.docs.append(doc)
        n = self._index(doc_id, content)
        doc['chunks'] = n
        return doc

    def delete_document(self, doc_id: int) -> bool:
        self.docs = [d for d in self.docs if d['id'] != doc_id]
        keep = [i for i, did in enumerate(self.chunk_dids) if did != doc_id]
        self.chunks     = [self.chunks[i]     for i in keep]
        self.chunk_dids = [self.chunk_dids[i] for i in keep]
        if keep:
            self.vectors = self.vectors[keep] if self.vectors is not None else None
        else:
            self.vectors = None
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
        results = self.search(question, top_k=5)

        if not results:
            return {
                'answer':     'База знаний пуста. Загрузите документы.',
                'sources':    [],
                'confidence': 0.0,
                'found':      False,
            }

        best_score = results[0]['score']
        if best_score < 0.12:
            return {
                'answer':     f'По запросу «{question}» ничего не найдено. Попробуйте переформулировать.',
                'sources':    [],
                'confidence': round(best_score * 100, 1),
                'found':      False,
            }

        # Извлекаем лучшие предложения
        q_words       = set(re.findall(r'\b\w+\b', question.lower()))
        scored_sents  = []
        used_sources  = []

        for r in results[:3]:
            if r['score'] < 0.10:
                continue
            for sent in re.split(r'[.!?\n]+', r['chunk']):
                sent = sent.strip()
                if len(sent) < 20:
                    continue
                sw      = set(re.findall(r'\b\w+\b', sent.lower()))
                overlap = len(q_words & sw) / max(len(q_words), 1)
                scored_sents.append((overlap, sent, r['doc_name']))
            if r['doc_name'] not in used_sources:
                used_sources.append(r['doc_name'])

        scored_sents.sort(key=lambda x: -x[0])

        seen, lines = set(), []
        for _, sent, _ in scored_sents[:4]:
            if sent not in seen:
                seen.add(sent)
                lines.append(sent)

        if not lines:
            # Fallback: первые предложения лучшего чанка
            raw = results[0]['chunk']
            lines = [s.strip() for s in raw.split('.') if len(s.strip()) > 20][:3]

        answer = ' '.join(lines)
        if used_sources:
            answer += f'\n\n📄 Источник: {", ".join(used_sources[:2])}'

        return {
            'answer':     answer,
            'sources':    used_sources,
            'confidence': round(best_score * 100, 1),
            'found':      True,
        }

    def stats(self) -> Dict:
        enc_params = sum(p.numel() for p in self.encoder.parameters())
        return {
            'total_docs':     len(self.docs),
            'total_chunks':   len(self.chunks),
            'vocab_size':     len(self.tok.vocab),
            'encoder_params': enc_params,
            'has_index':      self.vectors is not None,
            'embedding_dim':  128,
        }

    # ── Internal ─────────────────────────────────────

    def _index(self, doc_id: int, text: str,
               chunk_size: int = 150, overlap: int = 50) -> int:
        words  = text.split()
        step   = max(1, chunk_size - overlap)
        chunks = []
        for i in range(0, max(1, len(words)), step):
            chunk = ' '.join(words[i:i + chunk_size])
            if len(chunk.strip()) > 15:
                chunks.append(chunk)
        if not chunks:
            chunks = [text[:500]]

        # Обучаем токенизатор на всех текстах
        all_texts = [d['content'] for d in self.docs] + chunks
        self.tok.fit(all_texts)

        # Добавляем в хранилище
        self.chunks.extend(chunks)
        self.chunk_dids.extend([doc_id] * len(chunks))

        # Пересчитываем все векторы (токенизатор мог измениться)
        self.vectors = self._encode(self.chunks)
        return len(chunks)

    def _encode(self, texts: List[str]) -> torch.Tensor:
        if not texts:
            return torch.zeros(0, 128)
        all_vecs = []
        with torch.no_grad():
            for i in range(0, len(texts), 32):
                batch       = texts[i:i + 32]
                ids, masks  = self.tok.encode_batch(batch)
                ids, masks  = ids.to(self.device), masks.to(self.device)
                all_vecs.append(self.encoder(ids, masks).cpu())
        return torch.cat(all_vecs, dim=0)

    def _load_demo_docs(self):
        demo = [
            ("Политика безопасности", "Безопасность",
             "Политика информационной безопасности компании версия 2.1. "
             "Все пароли должны содержать минимум 12 символов, включать буквы, цифры и спецсимволы. "
             "Пароли необходимо менять каждые 90 дней. "
             "Двухфакторная аутентификация обязательна для всех сотрудников. "
             "VPN обязателен при работе вне офиса. "
             "Запрещено устанавливать программное обеспечение без согласования с IT-отделом. "
             "Инциденты безопасности сообщаются в IT в течение 1 часа. "
             "Конфиденциальные данные клиентов не передаются третьим лицам без письменного согласия руководства. "
             "Фишинговые письма пересылать на security@company.kz."),

            ("HR Процедуры", "HR",
             "Процедуры отдела кадров версия 3.0. "
             "Заявка на ежегодный отпуск подаётся минимум за 14 дней, форма ФО-07 в системе 1С. "
             "Согласование с руководителем, финальное подтверждение от HR в течение 3 рабочих дней. "
             "Ежегодный оплачиваемый отпуск 28 дней. "
             "Больничный лист сдаётся в HR в течение 5 рабочих дней после выхода. "
             "Дресс-код: smart casual в офисе, деловой стиль при встречах с клиентами. Джинсы разрешены по пятницам. "
             "Испытательный срок 3 месяца. Корпоративная медицинская страховка с первого дня. "
             "По всем вопросам: hr@company.kz"),

            ("Финансовый регламент", "Финансы",
             "Финансовые правила компании версия 1.5. "
             "Корпоративная карта оформляется через бухгалтерию по форме ФН-12, срок оформления 5 рабочих дней. "
             "Лимит по карте для сотрудников 50000 тенге в месяц, для руководителей 150000 тенге. "
             "Все расходы требуют чеков и подтверждающих документов. "
             "Авансовый отчёт сдаётся до 5-го числа следующего месяца. "
             "Командировочные суточные 5000 тенге. Проживание до 20000 тенге в сутки. "
             "Представительские расходы свыше 30000 тенге согласовываются с директором."),

            ("Кодекс этики", "Этика",
             "Кодекс корпоративного поведения и этики. "
             "Уважительное отношение ко всем сотрудникам независимо от должности обязательно. "
             "Конфликт интересов необходимо сообщать руководству в письменном виде. "
             "Запрещено принимать подарки от клиентов и партнёров стоимостью свыше 5000 тенге. "
             "Конфиденциальность информации сохраняется в течение 2 лет после увольнения. "
             "Нарушение кодекса влечёт дисциплинарное взыскание вплоть до увольнения."),

            ("IT Безопасность", "IT",
             "Регламент IT-безопасности версия 2.0. "
             "VPN обязателен при удалённой работе и подключении к публичным WiFi-сетям. "
             "Запрещено устанавливать программное обеспечение без согласования с IT-отделом. "
             "Корпоративная электронная почта используется только для рабочих целей. "
             "Рабочие файлы хранятся только на корпоративных серверах. "
             "Мобильные устройства с корпоративным доступом должны иметь PIN-код или биометрию. "
             "Фишинговые и подозрительные письма пересылать на security@company.kz. "
             "Пароли от корпоративных систем менять каждые 90 дней."),
        ]
        for name, cat, content in demo:
            self.add_document(name, content, cat)