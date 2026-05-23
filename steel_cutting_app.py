#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=================================================================
نظام توليف وقص الحديد الذكي
Steel Cutting Optimization & Inventory Management System
=================================================================

وصف:
    نظام متكامل لإدارة عمليات تقطيع الحديد باستخدام خوارزميات
    تحسين متقدمة لتقليل الهدر وتوليد أفضل توليفات القص.

الإصدار: 1.0.0
التاريخ: 2026-05-23
"""

import sqlite3
import json
import os
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# ============================================================
# CONFIGURATION
# ============================================================

COLORS = [
    '#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
    '#1abc9c', '#e67e22', '#34495e', '#16a085', '#c0392b',
    '#2980b9', '#27ae60', '#d35400', '#8e44ad', '#2c3e50'
]

DB_PATH = 'steel_cutting_db.sqlite'

# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class RequiredPiece:
    name: str
    length: float
    quantity: int
    piece_type: str
    color: str = None

@dataclass
class StockBar:
    length: float
    bar_type: str
    quantity_available: int = float('inf')

@dataclass
class CutPattern:
    stock_length: float
    pieces: List[Dict]
    waste: float
    stock_type: str

@dataclass
class InventoryItem:
    id: int
    name: str
    length: float
    piece_type: str
    quantity: int
    source_cut_id: Optional[int] = None
    date_added: str = None
    is_used: bool = False

# ============================================================
# DATABASE MANAGER
# ============================================================

class DatabaseManager:
    """مدير قاعدة البيانات SQLite"""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_database()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_database(self):
        """تهيئة قاعدة البيانات"""
        if os.path.exists(self.db_path):
            return

        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE material_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                diameter REAL,
                standard_length REAL,
                unit TEXT DEFAULT 'cm',
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                client_name TEXT,
                created_date DATE DEFAULT CURRENT_DATE,
                status TEXT DEFAULT 'active',
                notes TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE required_pieces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                material_type_id INTEGER NOT NULL,
                piece_name TEXT NOT NULL,
                length REAL NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                color_code TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id),
                FOREIGN KEY (material_type_id) REFERENCES material_types(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_type_id INTEGER NOT NULL,
                piece_name TEXT,
                length REAL NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                source_cut_id INTEGER,
                date_added DATE DEFAULT CURRENT_DATE,
                is_used BOOLEAN DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                notes TEXT,
                FOREIGN KEY (material_type_id) REFERENCES material_types(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE cutting_operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                operation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                material_type_id INTEGER NOT NULL,
                stock_length REAL NOT NULL,
                stock_type TEXT,
                total_waste REAL DEFAULT 0,
                utilization_rate REAL,
                operator_name TEXT,
                notes TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id),
                FOREIGN KEY (material_type_id) REFERENCES material_types(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE cutting_details (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_id INTEGER NOT NULL,
                piece_name TEXT NOT NULL,
                length REAL NOT NULL,
                position_order INTEGER,
                color_code TEXT,
                from_inventory BOOLEAN DEFAULT 0,
                inventory_id INTEGER,
                FOREIGN KEY (operation_id) REFERENCES cutting_operations(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE inventory_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inventory_id INTEGER,
                transaction_type TEXT NOT NULL,
                quantity_change INTEGER NOT NULL,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                operation_id INTEGER,
                user_name TEXT,
                notes TEXT,
                FOREIGN KEY (inventory_id) REFERENCES inventory(id),
                FOREIGN KEY (operation_id) REFERENCES cutting_operations(id)
            )
        ''')

        cursor.execute('CREATE INDEX idx_inventory_type ON inventory(material_type_id, is_active)')
        cursor.execute('CREATE INDEX idx_cutting_date ON cutting_operations(operation_date)')
        cursor.execute('CREATE INDEX idx_cutting_project ON cutting_operations(project_id)')
        cursor.execute('CREATE INDEX idx_required_project ON required_pieces(project_id)')

        materials = [
            ('حديد تسليح 12mm', 12, 1200, 'mm', 'حديد تسليح قطر 12 مم'),
            ('حديد تسليح 16mm', 16, 1200, 'mm', 'حديد تسليح قطر 16 مم'),
            ('حديد تسليح 20mm', 20, 1200, 'mm', 'حديد تسليح قطر 20 مم'),
        ]
        cursor.executemany('''
            INSERT INTO material_types (name, diameter, standard_length, unit, description)
            VALUES (?, ?, ?, ?, ?)
        ''', materials)

        conn.commit()
        conn.close()
        print("تم إنشاء قاعدة البيانات بنجاح")

# ============================================================
# CUTTING OPTIMIZER
# ============================================================

class CuttingOptimizer:
    """محرك التوليف الأمثل"""

    def __init__(self, stock_bars: List[StockBar], inventory: List[InventoryItem] = None):
        self.stock_bars = sorted(stock_bars, key=lambda x: x.length)
        self.inventory = inventory or []
        self.color_map = {}

    def _get_color(self, name: str) -> str:
        if name not in self.color_map:
            self.color_map[name] = COLORS[len(self.color_map) % len(COLORS)]
        return self.color_map[name]

    def _create_piece_list(self, requirements: List[RequiredPiece]) -> List[Dict]:
        pieces = []
        for req in requirements:
            color = self._get_color(req.name)
            for _ in range(req.quantity):
                pieces.append({
                    'name': req.name,
                    'length': req.length,
                    'type': req.piece_type,
                    'color': color
                })
        pieces.sort(key=lambda x: x['length'], reverse=True)
        return pieces

    def _try_inventory(self, pieces: List[Dict]) -> Tuple[List[CutPattern], List[Dict]]:
        used = []
        remaining = []
        inv_copy = [item for item in self.inventory if item.quantity > 0 and not item.is_used]

        for piece in pieces:
            assigned = False
            for inv_item in inv_copy:
                if (abs(inv_item.length - piece['length']) < 1 and 
                    inv_item.piece_type == piece['type'] and
                    inv_item.quantity > 0):

                    pattern = CutPattern(
                        stock_length=inv_item.length,
                        pieces=[{
                            'name': piece['name'],
                            'length': piece['length'],
                            'color': piece['color'],
                            'from_inventory': True,
                            'inventory_id': inv_item.id
                        }],
                        waste=inv_item.length - piece['length'],
                        stock_type=f"مخزن #{inv_item.id}"
                    )
                    used.append(pattern)
                    inv_item.quantity -= 1
                    assigned = True
                    break

            if not assigned:
                remaining.append(piece)

        return used, remaining

    def optimize(self, requirements: List[RequiredPiece], use_inventory: bool = True) -> Dict:
        all_pieces = self._create_piece_list(requirements)
        patterns = []

        if use_inventory and self.inventory:
            inv_patterns, all_pieces = self._try_inventory(all_pieces)
            patterns.extend(inv_patterns)

        remaining = all_pieces[:]

        while remaining:
            best_combo = None
            best_waste = float('inf')
            best_stock = None

            for stock in self.stock_bars:
                combo, waste = self._fill_greedy(remaining, stock.length)
                if combo and waste < best_waste:
                    best_waste = waste
                    best_combo = combo
                    best_stock = stock

                if len(remaining) >= 2:
                    combo2, waste2 = self._local_search(remaining, stock.length)
                    if combo2 and waste2 < best_waste:
                        best_waste = waste2
                        best_combo = combo2
                        best_stock = stock

            if best_combo and best_stock:
                pattern = CutPattern(
                    stock_length=best_stock.length,
                    pieces=best_combo,
                    waste=best_waste,
                    stock_type=best_stock.bar_type
                )
                patterns.append(pattern)

                for p in best_combo:
                    for i, r in enumerate(remaining):
                        if r['name'] == p['name'] and abs(r['length'] - p['length']) < 0.01:
                            remaining.pop(i)
                            break
            else:
                break

        total_waste = sum(p.waste for p in patterns)
        total_stock = sum(p.stock_length for p in patterns)
        total_required = sum(req.length * req.quantity for req in requirements)
        utilization = (total_required / total_stock * 100) if total_stock > 0 else 0

        return {
            'patterns': patterns,
            'unassigned': remaining,
            'stats': {
                'total_patterns': len(patterns),
                'total_waste': total_waste,
                'total_stock_length': total_stock,
                'total_required_length': total_required,
                'utilization_rate': round(utilization, 2),
                'waste_percentage': round(100 - utilization, 2),
                'inventory_used': len([p for p in patterns if any('from_inventory' in x for x in p.pieces)])
            }
        }

    def _fill_greedy(self, pieces: List[Dict], stock_length: float) -> Tuple[List[Dict], float]:
        combo = []
        remaining = stock_length

        for piece in pieces:
            if piece['length'] <= remaining:
                combo.append(piece.copy())
                remaining -= piece['length']
                if remaining < 0.1:
                    break

        if not combo:
            return None, float('inf')

        waste = stock_length - sum(p['length'] for p in combo)
        return combo, waste

    def _local_search(self, pieces: List[Dict], stock_length: float) -> Tuple[List[Dict], float]:
        best_combo, best_waste = self._fill_greedy(pieces, stock_length)

        if not best_combo or len(pieces) < 2:
            return best_combo, best_waste

        for i in range(min(5, len(pieces))):
            for j in range(i+1, min(5, len(pieces))):
                test = pieces[:]
                test[i], test[j] = test[j], test[i]
                combo, waste = self._fill_greedy(test, stock_length)
                if combo and waste < best_waste:
                    best_combo = combo
                    best_waste = waste

        return best_combo, best_waste

# ============================================================
# INVENTORY MANAGER
# ============================================================

class InventoryManager:
    """نظام إدارة المخزن"""

    def __init__(self, db_manager: DatabaseManager = None):
        self.db = db_manager or DatabaseManager()
        self.next_id = 1

    def add_item(self, name: str, length: float, piece_type: str, quantity: int = 1,
                 source_cut_id: int = None) -> int:
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO inventory (material_type_id, piece_name, length, quantity, source_cut_id, date_added)
            VALUES ((SELECT id FROM material_types WHERE name LIKE ? LIMIT 1), ?, ?, ?, ?, ?)
        ''', (f'%{piece_type}%', name, length, quantity, source_cut_id, datetime.now().strftime('%Y-%m-%d')))

        item_id = cursor.lastrowid

        cursor.execute('''
            INSERT INTO inventory_transactions (inventory_id, transaction_type, quantity_change, notes)
            VALUES (?, 'add', ?, ?)
        ''', (item_id, quantity, f"إضافة: {name}"))

        conn.commit()
        conn.close()
        return item_id

    def use_item(self, item_id: int, quantity: int = 1) -> bool:
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT quantity FROM inventory WHERE id = ? AND is_active = 1', (item_id,))
        result = cursor.fetchone()

        if not result or result[0] < quantity:
            conn.close()
            return False

        new_qty = result[0] - quantity
        cursor.execute('''
            UPDATE inventory SET quantity = ?, is_used = ? WHERE id = ?
        ''', (new_qty, 1 if new_qty == 0 else 0, item_id))

        cursor.execute('''
            INSERT INTO inventory_transactions (inventory_id, transaction_type, quantity_change, notes)
            VALUES (?, 'use', ?, ?)
        ''', (item_id, -quantity, f"استخدام {quantity}"))

        conn.commit()
        conn.close()
        return True

    def get_available(self, piece_type: str = None) -> List[InventoryItem]:
        conn = self.db.get_connection()
        cursor = conn.cursor()

        if piece_type:
            cursor.execute('''
                SELECT i.* FROM inventory i
                JOIN material_types m ON i.material_type_id = m.id
                WHERE i.quantity > 0 AND i.is_active = 1 AND m.name LIKE ?
            ''', (f'%{piece_type}%',))
        else:
            cursor.execute('''
                SELECT * FROM inventory WHERE quantity > 0 AND is_active = 1
            ''')

        rows = cursor.fetchall()
        conn.close()

        items = []
        for row in rows:
            items.append(InventoryItem(
                id=row[0], name=row[2], length=row[3], piece_type="",
                quantity=row[4], source_cut_id=row[5], date_added=row[6], is_used=row[7]
            ))
        return items

    def delete_item(self, item_id: int) -> bool:
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute('UPDATE inventory SET is_active = 0 WHERE id = ?', (item_id,))

        cursor.execute('''
            INSERT INTO inventory_transactions (inventory_id, transaction_type, quantity_change, notes)
            VALUES (?, 'delete', 0, ?)
        ''', (item_id, "حذف"))

        conn.commit()
        conn.close()
        return True

# ============================================================
# VISUALIZER
# ============================================================

class CuttingVisualizer:
    """محرك الرسومات"""

    def __init__(self):
        plt.rcParams['font.family'] = 'DejaVu Sans'
        plt.rcParams['axes.unicode_minus'] = False

    def draw_patterns(self, result: Dict, title: str = "خطة القص", save_path: str = None) -> plt.Figure:
        patterns = result['patterns']
        if not patterns:
            return None

        n = len(patterns)
        fig_height = max(6, n * 1.5)
        fig, axes = plt.subplots(n, 1, figsize=(14, fig_height))

        if n == 1:
            axes = [axes]

        for idx, (ax, pattern) in enumerate(zip(axes, patterns)):
            self._draw_bar(ax, pattern, idx + 1)

        fig.suptitle(title, fontsize=16, fontweight='bold', y=1.02)
        plt.tight_layout()

        if save_path:
            fig.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)

        return fig

    def _draw_bar(self, ax, pattern: CutPattern, num: int):
        stock = pattern.stock_length
        ax.add_patch(patches.Rectangle((0, 0), stock, 1, linewidth=2, 
                                       edgecolor='black', facecolor='#ecf0f1'))

        current_x = 0
        for piece in pattern.pieces:
            color = piece.get('color', '#3498db')
            length = piece['length']

            rect = patches.Rectangle((current_x, 0.05), length, 0.9,
                                     linewidth=1, edgecolor='black',
                                     facecolor=color, alpha=0.8)
            ax.add_patch(rect)

            ax.text(current_x + length/2, 0.5, 
                   f"{piece['name']}\n{length}cm",
                   ha='center', va='center', fontsize=9, fontweight='bold',
                   color='white' if self._is_dark(color) else 'black')

            current_x += length

        if pattern.waste > 0.5:
            ax.add_patch(patches.Rectangle((current_x, 0.05), pattern.waste, 0.9,
                                           linewidth=1, edgecolor='black',
                                           facecolor='#e74c3c', alpha=0.5, hatch='///'))
            ax.text(current_x + pattern.waste/2, 0.5, 
                   f"هدر\n{pattern.waste:.1f}cm",
                   ha='center', va='center', fontsize=8, color='white', fontweight='bold')

        ax.set_xlim(-2, stock + 2)
        ax.set_ylim(-0.3, 1.4)
        ax.set_yticks([])
        ax.set_xlabel('الطول (سم)', fontsize=10)

        inv = " [مخزن]" if any('from_inventory' in p for p in pattern.pieces) else ""
        ax.set_title(f"قضيب #{num} - {pattern.stock_type} ({stock}cm){inv}", 
                    fontsize=11, loc='right')

        util = (stock - pattern.waste) / stock * 100
        ax.text(stock + 1, 0.5, f"استغلال: {util:.1f}%", 
               fontsize=9, va='center', color='#27ae60', fontweight='bold')

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)

    def _is_dark(self, color: str) -> bool:
        try:
            rgb = plt.cm.colors.to_rgb(color)
            lum = 0.299*rgb[0] + 0.587*rgb[1] + 0.114*rgb[2]
            return lum < 0.5
        except:
            return False

    def draw_summary(self, result: Dict, save_path: str = None) -> plt.Figure:
        stats = result['stats']
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))

        ax1 = axes[0]
        sizes = [stats['utilization_rate'], stats['waste_percentage']]
        labels = [f'استغلال\n{stats["utilization_rate"]}%', f'هدر\n{stats["waste_percentage"]}%']
        colors = ['#2ecc71', '#e74c3c']
        ax1.pie(sizes, labels=labels, colors=colors, autopct='',
                shadow=True, startangle=90, textprops={'fontsize': 11, 'fontweight': 'bold'})
        ax1.set_title('نسبة استغلال المواد', fontsize=13, fontweight='bold')

        ax2 = axes[1]
        categories = ['القضبان', 'المستخدم', 'المطلوب', 'الهدر']
        values = [
            stats['total_patterns'],
            stats['total_stock_length'],
            stats['total_required_length'],
            stats['total_waste']
        ]
        bars = ax2.bar(categories, values, color=['#3498db', '#9b59b6', '#2ecc71', '#e74c3c'])
        ax2.set_title('إحصائيات القص', fontsize=13, fontweight='bold')
        ax2.set_ylabel('القيمة')

        for bar, val in zip(bars, values):
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height,
                    f'{val:.1f}', ha='center', va='bottom', fontsize=10, fontweight='bold')

        plt.tight_layout()

        if save_path:
            fig.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)

        return fig

# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("نظام توليف وقص الحديد الذكي v1.0")
    print("=" * 60)

    db = DatabaseManager()
    inv_manager = InventoryManager(db)
    inv_manager.add_item("باقي_قديم", 120, "12mm", 2)
    inv_manager.add_item("باقي_قديم", 85, "12mm", 1)

    stock = [
        StockBar(600, "حديد 12mm 6م"),
        StockBar(1200, "حديد 12mm 12م"),
        StockBar(600, "حديد 16mm 6م"),
    ]

    requirements = [
        RequiredPiece("عمود_A1", 350, 4, "حديد_12mm"),
        RequiredPiece("عمود_A2", 280, 3, "حديد_12mm"),
        RequiredPiece("سقف_B1", 180, 6, "حديد_12mm"),
        RequiredPiece("سقف_B2", 120, 5, "حديد_12mm"),
        RequiredPiece("كمر_C1", 420, 2, "حديد_16mm"),
        RequiredPiece("كمر_C2", 310, 2, "حديد_16mm"),
    ]

    inventory_items = inv_manager.get_available("12mm")
    optimizer = CuttingOptimizer(stock, inventory_items)
    result = optimizer.optimize(requirements, use_inventory=True)

    print(f"\nالنتائج:")
    print(f"   عدد القضبان: {result['stats']['total_patterns']}")
    print(f"   نسبة الاستغلال: {result['stats']['utilization_rate']}%")
    print(f"   نسبة الهدر: {result['stats']['waste_percentage']}%")
    print(f"   إجمالي الهدر: {result['stats']['total_waste']:.1f} سم")

    for i, pattern in enumerate(result['patterns']):
        if pattern.waste > 20:
            inv_manager.add_item(
                f"باقي_قص_{i+1}", 
                pattern.waste, 
                pattern.stock_type.split('_')[1] if '_' in pattern.stock_type else "عام",
                1,
                i+1
            )

    viz = CuttingVisualizer()
    viz.draw_patterns(result, "خطة القص", "cutting_patterns.png")
    viz.draw_summary(result, "summary_chart.png")

    print("\nتم إنشاء الرسومات:")
    print("   cutting_patterns.png")
    print("   summary_chart.png")

if __name__ == "__main__":
    main()
