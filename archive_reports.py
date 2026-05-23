
# ============================================================
# ARCHIVE & SEARCH SYSTEM
# ============================================================

class ArchiveManager:
    """نظام الأرشيف والبحث المتقدم"""

    def __init__(self, db_manager):
        self.db = db_manager

    def save_cutting_operation(self, project_id: int, material_type_id: int,
                               result: Dict, operator_name: str = None) -> int:
        """حفظ عملية قص في الأرشيف"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        stats = result['stats']
        cursor.execute('''
            INSERT INTO cutting_operations 
            (project_id, material_type_id, stock_length, stock_type, 
             total_waste, utilization_rate, operator_name, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (project_id, material_type_id, stats['total_stock_length'],
              'mixed', stats['total_waste'], stats['utilization_rate'],
              operator_name, f"عملية قص: {stats['total_patterns']} قضبان"))

        op_id = cursor.lastrowid

        # حفظ تفاصيل القطع
        for i, pattern in enumerate(result['patterns']):
            for j, piece in enumerate(pattern.pieces):
                cursor.execute('''
                    INSERT INTO cutting_details 
                    (operation_id, piece_name, length, position_order, 
                     color_code, from_inventory, inventory_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (op_id, piece['name'], piece['length'], j,
                      piece.get('color', '#3498db'),
                      piece.get('from_inventory', False),
                      piece.get('inventory_id')))

        conn.commit()
        conn.close()
        return op_id

    def search_operations(self, date_from: str = None, date_to: str = None,
                          material_type: str = None, piece_name: str = None,
                          project_id: int = None) -> List[Dict]:
        """البحث في الأرشيف"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        query = '''
            SELECT co.*, p.project_name, mt.name as material_name
            FROM cutting_operations co
            LEFT JOIN projects p ON co.project_id = p.id
            LEFT JOIN material_types mt ON co.material_type_id = mt.id
            WHERE 1=1
        '''
        params = []

        if date_from:
            query += ' AND co.operation_date >= ?'
            params.append(date_from)
        if date_to:
            query += ' AND co.operation_date <= ?'
            params.append(date_to)
        if material_type:
            query += ' AND mt.name LIKE ?'
            params.append(f'%{material_type}%')
        if piece_name:
            query += ''' AND co.id IN (
                SELECT operation_id FROM cutting_details 
                WHERE piece_name LIKE ?
            )'''
            params.append(f'%{piece_name}%')
        if project_id:
            query += ' AND co.project_id = ?'
            params.append(project_id)

        query += ' ORDER BY co.operation_date DESC'

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        operations = []
        for row in rows:
            operations.append({
                'id': row[0],
                'project_id': row[1],
                'project_name': row[-2],
                'date': row[3],
                'material': row[-1],
                'waste': row[7],
                'utilization': row[8],
                'operator': row[9]
            })
        return operations

    def get_inventory_history(self, item_id: int = None, 
                              date_from: str = None, date_to: str = None) -> List[Dict]:
        """الحصول على حركة المخزن"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        query = '''
            SELECT t.*, i.piece_name, i.length
            FROM inventory_transactions t
            JOIN inventory i ON t.inventory_id = i.id
            WHERE 1=1
        '''
        params = []

        if item_id:
            query += ' AND t.inventory_id = ?'
            params.append(item_id)
        if date_from:
            query += ' AND t.date >= ?'
            params.append(date_from)
        if date_to:
            query += ' AND t.date <= ?'
            params.append(date_to)

        query += ' ORDER BY t.date DESC'

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        transactions = []
        for row in rows:
            transactions.append({
                'id': row[0],
                'item_id': row[1],
                'item_name': row[-2],
                'item_length': row[-1],
                'type': row[2],
                'quantity_change': row[3],
                'date': row[4],
                'notes': row[7]
            })
        return transactions

# ============================================================
# REPORTS ENGINE
# ============================================================

class ReportsEngine:
    """محرك التقارير والطباعة"""

    def __init__(self, db_manager):
        self.db = db_manager

    def generate_waste_report(self, date_from: str, date_to: str) -> Dict:
        """تقرير تحليل الهدر"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT material_type_id, 
                   COUNT(*) as operation_count,
                   SUM(total_waste) as total_waste,
                   AVG(utilization_rate) as avg_utilization
            FROM cutting_operations
            WHERE operation_date BETWEEN ? AND ?
            GROUP BY material_type_id
        ''', (date_from, date_to))

        rows = cursor.fetchall()
        conn.close()

        report = {
            'period': f"{date_from} to {date_to}",
            'summary_by_material': [],
            'total_operations': 0,
            'total_waste': 0
        }

        for row in rows:
            report['summary_by_material'].append({
                'material_id': row[0],
                'operations': row[1],
                'total_waste': row[2],
                'avg_utilization': round(row[3], 2)
            })
            report['total_operations'] += row[1]
            report['total_waste'] += row[2]

        return report

    def generate_inventory_report(self) -> Dict:
        """تقرير المخزن الحالي"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT i.*, mt.name as material_name
            FROM inventory i
            JOIN material_types mt ON i.material_type_id = mt.id
            WHERE i.is_active = 1
            ORDER BY mt.name, i.length DESC
        ''')

        rows = cursor.fetchall()
        conn.close()

        report = {
            'total_items': len(rows),
            'total_length': sum(r[3] * r[4] for r in rows),
            'items_by_material': {}
        }

        for row in rows:
            material = row[-1]
            if material not in report['items_by_material']:
                report['items_by_material'][material] = []

            report['items_by_material'][material].append({
                'id': row[0],
                'name': row[2],
                'length': row[3],
                'quantity': row[4],
                'status': 'مستخدم' if row[7] else 'متاح'
            })

        return report

    def print_cutting_plan(self, result: Dict, project_name: str = "مشروع") -> str:
        """توليد نص طباعة منسق"""
        stats = result['stats']

        output = f"""
{'='*70}
خطة القص - {project_name}
{'='*70}
التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}

الإحصائيات:
  - عدد القضبان المستخدمة: {stats['total_patterns']}
  - نسبة الاستغلال: {stats['utilization_rate']}%
  - نسبة الهدر: {stats['waste_percentage']}%
  - إجمالي الهدر: {stats['total_waste']:.1f} سم
  - القطع من المخزن: {stats['inventory_used']}

تفاصيل القص:
{'='*70}
"""

        for i, pattern in enumerate(result['patterns'], 1):
            inv_marker = " [مخزن]" if any('from_inventory' in p for p in pattern.pieces) else ""
            output += f"\nقضيب #{i}: {pattern.stock_type} ({pattern.stock_length}cm){inv_marker}\n"

            for j, piece in enumerate(pattern.pieces, 1):
                output += f"  {j}. {piece['name']}: {piece['length']}cm\n"

            if pattern.waste > 0.5:
                output += f"  هدر: {pattern.waste:.1f}cm\n"

            util = (pattern.stock_length - pattern.waste) / pattern.stock_length * 100
            output += f"  نسبة الاستغلال: {util:.1f}%\n"
            output += "-" * 50 + "\n"

        output += f"""
{'='*70}
ملاحظات للمشغل:
- راجع القياسات قبل القص
- احفظ الهدر المجري (>20سم) في المخزن
- تأكد من تطابق نوع المادة
{'='*70}
"""

        return output
