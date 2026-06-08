"""
Vision AI — Собственная свёрточная нейросеть (CNN) на PyTorch
Архитектура: VisionNet — глубокая CNN с Residual Connections

Структура:
  - ConvBlock: Conv2d → BatchNorm → ReLU → Dropout
  - ResidualBlock: пропускное соединение (skip connection)
  - VisionNet: глубокая CNN для классификации изображений
  - Поддержка: CIFAR-10, MNIST, собственных датасетов
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torchvision import datasets, transforms
from torch.utils.data import DataLoader, random_split
import numpy as np
import json
import os
import time
from typing import List, Tuple, Dict, Optional


# ──────────────────────────────────────────────
#  БЛОК 1: Базовый свёрточный блок
# ──────────────────────────────────────────────
class ConvBlock(nn.Module):
    """Conv2d → BatchNorm2d → ReLU → Dropout"""
    def __init__(self, in_ch: int, out_ch: int, kernel: int = 3,
                 stride: int = 1, padding: int = 1, dropout: float = 0.1):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, kernel, stride, padding, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Dropout2d(dropout),
        )

    def forward(self, x):
        return self.block(x)


# ──────────────────────────────────────────────
#  БЛОК 2: Residual Block (ResNet-style)
# ──────────────────────────────────────────────
class ResidualBlock(nn.Module):
    """
    Блок с пропускным соединением (skip connection).
    Помогает обучать глубокие сети без деградации градиентов.
    F(x) + x — если размерности совпадают
    F(x) + proj(x) — если нужна проекция
    """
    def __init__(self, in_ch: int, out_ch: int, stride: int = 1):
        super().__init__()
        self.conv1 = nn.Conv2d(in_ch, out_ch, 3, stride, 1, bias=False)
        self.bn1   = nn.BatchNorm2d(out_ch)
        self.conv2 = nn.Conv2d(out_ch, out_ch, 3, 1, 1, bias=False)
        self.bn2   = nn.BatchNorm2d(out_ch)
        self.relu  = nn.ReLU(inplace=True)
        self.drop  = nn.Dropout2d(0.1)

        # Проекция для согласования размерностей
        self.shortcut = nn.Sequential()
        if stride != 1 or in_ch != out_ch:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_ch, out_ch, 1, stride, bias=False),
                nn.BatchNorm2d(out_ch),
            )

    def forward(self, x):
        out = self.relu(self.bn1(self.conv1(x)))
        out = self.drop(out)
        out = self.bn2(self.conv2(out))
        out += self.shortcut(x)   # ← skip connection
        return self.relu(out)


# ──────────────────────────────────────────────
#  БЛОК 3: Squeeze-and-Excitation (внимание по каналам)
# ──────────────────────────────────────────────
class SEBlock(nn.Module):
    """
    Channel Attention: учим сеть акцентировать важные каналы.
    Global Avg Pool → FC → ReLU → FC → Sigmoid → scale
    """
    def __init__(self, channels: int, reduction: int = 16):
        super().__init__()
        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.fc = nn.Sequential(
            nn.Linear(channels, channels // reduction, bias=False),
            nn.ReLU(inplace=True),
            nn.Linear(channels // reduction, channels, bias=False),
            nn.Sigmoid(),
        )

    def forward(self, x):
        B, C, _, _ = x.size()
        w = self.avg_pool(x).view(B, C)
        w = self.fc(w).view(B, C, 1, 1)
        return x * w.expand_as(x)


# ──────────────────────────────────────────────
#  БЛОК 4: VisionNet — главная CNN
# ──────────────────────────────────────────────
class VisionNet(nn.Module):
    """
    Собственная глубокая CNN для классификации изображений.

    Архитектура (для 32×32 входа — CIFAR-10):
      Stem: Conv 3→64
      Stage 1: ResBlock 64→64  + SE
      Stage 2: ResBlock 64→128 + SE (stride=2, downsample)
      Stage 3: ResBlock 128→256 + SE (stride=2, downsample)
      Stage 4: ResBlock 256→512 + SE (stride=2, downsample)
      Head: GlobalAvgPool → FC(512→256) → FC(256→num_classes)

    Параметры: ~2.5M
    """
    def __init__(self, num_classes: int = 10, in_channels: int = 3,
                 input_size: int = 32):
        super().__init__()
        self.num_classes = num_classes
        self.input_size  = input_size

        # Stem
        self.stem = nn.Sequential(
            nn.Conv2d(in_channels, 64, 3, 1, 1, bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
        )

        # 4 стадии с Residual Blocks + SE Attention
        self.stage1 = nn.Sequential(ResidualBlock(64, 64),   SEBlock(64))
        self.stage2 = nn.Sequential(ResidualBlock(64, 128, stride=2),  SEBlock(128))
        self.stage3 = nn.Sequential(ResidualBlock(128, 256, stride=2), SEBlock(256))
        self.stage4 = nn.Sequential(ResidualBlock(256, 512, stride=2), SEBlock(512))

        # Classifier head
        self.global_pool = nn.AdaptiveAvgPool2d(1)
        self.classifier  = nn.Sequential(
            nn.Flatten(),
            nn.Linear(512, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            nn.Linear(256, num_classes),
        )

        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.Linear):
                nn.init.xavier_normal_(m.weight)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.stem(x)
        x = self.stage1(x)
        x = self.stage2(x)
        x = self.stage3(x)
        x = self.stage4(x)
        x = self.global_pool(x)
        x = self.classifier(x)
        return x

    def predict_proba(self, x: torch.Tensor) -> torch.Tensor:
        """Возвращает вероятности через softmax"""
        logits = self.forward(x)
        return F.softmax(logits, dim=-1)

    def count_params(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# ──────────────────────────────────────────────
#  БЛОК 5: Трейнер с метриками
# ──────────────────────────────────────────────
class VisionTrainer:
    """
    Полный цикл обучения: train → validate → сохранение лучшей модели.
    Поддерживает: CosineAnnealingLR, label smoothing, history логирование.
    """
    CIFAR10_CLASSES = [
        'самолёт', 'автомобиль', 'птица', 'кот', 'олень',
        'собака', 'лягушка', 'лошадь', 'корабль', 'грузовик',
    ]
    MNIST_CLASSES = [str(i) for i in range(10)]

    def __init__(self, dataset: str = 'cifar10', device: str = 'cpu',
                 save_dir: str = './checkpoints'):
        self.dataset   = dataset
        self.device    = torch.device(device)
        self.save_dir  = save_dir
        os.makedirs(save_dir, exist_ok=True)

        if dataset == 'cifar10':
            self.classes    = self.CIFAR10_CLASSES
            self.num_classes = 10
            self.in_channels = 3
            self.input_size  = 32
        else:  # mnist
            self.classes    = self.MNIST_CLASSES
            self.num_classes = 10
            self.in_channels = 1
            self.input_size  = 28

        self.model = VisionNet(
            num_classes=self.num_classes,
            in_channels=self.in_channels,
            input_size=self.input_size,
        ).to(self.device)

        self.history = {
            'train_loss': [], 'val_loss': [],
            'train_acc': [],  'val_acc': [],
        }
        self.best_val_acc = 0.0
        self.current_epoch = 0
        self.is_training = False
        self.training_callback = None  # для стриминга прогресса

    def _get_transforms(self, train: bool):
        if self.dataset == 'cifar10':
            if train:
                return transforms.Compose([
                    transforms.RandomCrop(32, padding=4),
                    transforms.RandomHorizontalFlip(),
                    transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
                    transforms.ToTensor(),
                    transforms.Normalize((0.4914, 0.4822, 0.4465),
                                         (0.2023, 0.1994, 0.2010)),
                ])
            return transforms.Compose([
                transforms.ToTensor(),
                transforms.Normalize((0.4914, 0.4822, 0.4465),
                                     (0.2023, 0.1994, 0.2010)),
            ])
        else:  # mnist
            return transforms.Compose([
                transforms.Resize(28),
                transforms.ToTensor(),
                transforms.Normalize((0.1307,), (0.3081,)),
            ])

    def load_data(self, batch_size: int = 64, val_split: float = 0.1):
        data_root = './data'
        if self.dataset == 'cifar10':
            train_ds = datasets.CIFAR10(data_root, train=True,
                                        download=True, transform=self._get_transforms(True))
            test_ds  = datasets.CIFAR10(data_root, train=False,
                                        download=True, transform=self._get_transforms(False))
        else:
            train_ds = datasets.MNIST(data_root, train=True,
                                      download=True, transform=self._get_transforms(True))
            test_ds  = datasets.MNIST(data_root, train=False,
                                      download=True, transform=self._get_transforms(False))

        # Разделяем train на train+val
        n_val = int(len(train_ds) * val_split)
        n_train = len(train_ds) - n_val
        train_ds, val_ds = random_split(train_ds, [n_train, n_val],
                                        generator=torch.Generator().manual_seed(42))

        self.train_loader = DataLoader(train_ds, batch_size=batch_size,
                                       shuffle=True, num_workers=0, pin_memory=False)
        self.val_loader   = DataLoader(val_ds, batch_size=batch_size,
                                       shuffle=False, num_workers=0)
        self.test_loader  = DataLoader(test_ds, batch_size=batch_size,
                                       shuffle=False, num_workers=0)
        return len(train_ds), len(val_ds), len(test_ds)

    def train(self, epochs: int = 20, lr: float = 0.001, batch_size: int = 64,
              weight_decay: float = 1e-4):
        """Основной цикл обучения"""
        self.load_data(batch_size)
        optimizer = optim.AdamW(self.model.parameters(), lr=lr, weight_decay=weight_decay)
        scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
        criterion = nn.CrossEntropyLoss(label_smoothing=0.1)

        self.is_training = True
        for epoch in range(1, epochs + 1):
            if not self.is_training:
                break
            self.current_epoch = epoch

            # ── Обучение ──
            self.model.train()
            train_loss, train_correct, total = 0.0, 0, 0
            for batch_idx, (images, labels) in enumerate(self.train_loader):
                images, labels = images.to(self.device), labels.to(self.device)
                optimizer.zero_grad()
                outputs = self.model(images)
                loss = criterion(outputs, labels)
                loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                optimizer.step()

                train_loss    += loss.item() * images.size(0)
                preds          = outputs.argmax(dim=1)
                train_correct += (preds == labels).sum().item()
                total         += images.size(0)

            train_loss /= total
            train_acc   = train_correct / total

            # ── Валидация ──
            val_loss, val_acc = self._evaluate(self.val_loader, criterion)
            scheduler.step()

            self.history['train_loss'].append(round(train_loss, 4))
            self.history['val_loss'].append(round(val_loss, 4))
            self.history['train_acc'].append(round(train_acc, 4))
            self.history['val_acc'].append(round(val_acc, 4))

            # Сохраняем лучшую модель
            if val_acc > self.best_val_acc:
                self.best_val_acc = val_acc
                self._save_checkpoint('best.pth')

            # Колбэк для стриминга прогресса во фронтенд
            if self.training_callback:
                self.training_callback({
                    'epoch': epoch, 'total_epochs': epochs,
                    'train_loss': round(train_loss, 4),
                    'val_loss': round(val_loss, 4),
                    'train_acc': round(train_acc * 100, 2),
                    'val_acc': round(val_acc * 100, 2),
                    'best_val_acc': round(self.best_val_acc * 100, 2),
                    'lr': round(scheduler.get_last_lr()[0], 6),
                })

        self.is_training = False
        self._save_checkpoint('last.pth')
        return self.history

    def _evaluate(self, loader, criterion) -> Tuple[float, float]:
        self.model.eval()
        total_loss, correct, total = 0.0, 0, 0
        with torch.no_grad():
            for images, labels in loader:
                images, labels = images.to(self.device), labels.to(self.device)
                outputs = self.model(images)
                loss = criterion(outputs, labels)
                total_loss += loss.item() * images.size(0)
                correct    += (outputs.argmax(1) == labels).sum().item()
                total      += images.size(0)
        return total_loss / total, correct / total

    def predict_image(self, image_tensor: torch.Tensor) -> Dict:
        """Предсказание для одного изображения"""
        self.model.eval()
        with torch.no_grad():
            image_tensor = image_tensor.unsqueeze(0).to(self.device)
            probs = self.model.predict_proba(image_tensor).squeeze(0).cpu().numpy()

        top5_idx   = probs.argsort()[::-1][:5]
        top5_preds = [
            {'class': self.classes[i], 'confidence': round(float(probs[i]) * 100, 2)}
            for i in top5_idx
        ]
        return {
            'prediction': self.classes[top5_idx[0]],
            'confidence': round(float(probs[top5_idx[0]]) * 100, 2),
            'top5': top5_preds,
            'all_probs': {self.classes[i]: round(float(p) * 100, 2)
                          for i, p in enumerate(probs)},
        }

    def get_model_info(self) -> Dict:
        total = self.model.count_params()
        return {
            'architecture': 'VisionNet (Custom CNN)',
            'total_params': total,
            'total_params_fmt': f'{total / 1e6:.2f}M',
            'dataset': self.dataset.upper(),
            'num_classes': self.num_classes,
            'classes': self.classes,
            'input_size': f'{self.in_channels}×{self.input_size}×{self.input_size}',
            'best_val_acc': round(self.best_val_acc * 100, 2),
            'current_epoch': self.current_epoch,
            'is_training': self.is_training,
            'history': self.history,
            'layers': {
                'stem': 'Conv2d(3→64) + BN + ReLU',
                'stage1': 'ResidualBlock(64→64) + SE Attention',
                'stage2': 'ResidualBlock(64→128, s=2) + SE Attention',
                'stage3': 'ResidualBlock(128→256, s=2) + SE Attention',
                'stage4': 'ResidualBlock(256→512, s=2) + SE Attention',
                'head': 'GlobalAvgPool → FC(512→256) → FC(256→10)',
            }
        }

    def stop_training(self):
        self.is_training = False

    def _save_checkpoint(self, filename: str):
        path = os.path.join(self.save_dir, filename)
        torch.save({
            'epoch': self.current_epoch,
            'model_state': self.model.state_dict(),
            'best_val_acc': self.best_val_acc,
            'history': self.history,
            'classes': self.classes,
            'dataset': self.dataset,
        }, path)

    def load_checkpoint(self, filename: str = 'best.pth') -> bool:
        path = os.path.join(self.save_dir, filename)
        if not os.path.exists(path):
            return False
        ckpt = torch.load(path, map_location=self.device)
        self.model.load_state_dict(ckpt['model_state'])
        self.best_val_acc = ckpt.get('best_val_acc', 0.0)
        self.current_epoch = ckpt.get('epoch', 0)
        self.history = ckpt.get('history', self.history)
        return True
